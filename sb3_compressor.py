#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SB3 Compressor - behavior-preserving compressor for Scratch (TurboWarp) .sb3 project files.

Python port of the Scratch project "sb3 Compressor".
  - Rename block IDs and variable/list/broadcast names to short IDs
  - Remove unused variables and lists
  - Shorten custom block proccodes and argument names
  - Remove default-valued fields that the VM reconstructs
  - Minify JSON and repack the .sb3 with its assets unchanged

Usage:
  python sb3_compressor.py                -> launch the GUI
  python sb3_compressor.py in.sb3 [out]   -> CLI mode
"""

from __future__ import annotations

import io
import json
import os
import queue
import re
import sys
import threading
import traceback
import zipfile

CLOUD_PREFIX = "\u2601"

# Built-in properties handled by sensing_of before its variable-name lookup.
# A variable with one of these names is shadowed on that target type, so the
# PROPERTY field must not be renamed to the variable's shortened name.
SENSING_STAGE_PROPERTIES = {"background #", "backdrop #", "backdrop name", "volume"}
SENSING_SPRITE_PROPERTIES = {"x position", "y position", "direction",
                             "costume #", "costume name", "size", "volume"}

_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"


class CompressError(Exception):
    pass


class Cancelled(Exception):
    pass


def encode_id(n: int) -> str:
    if n <= 0:
        n = 1
    out = ""
    while n:
        n, r = divmod(n - 1, 62)
        out = _ALPHABET[r] + out
    return out


def loose_eq(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if a is None or b is None:
        return a is None and b is None
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:,.1f} {unit}" if unit != "B" else f"{int(n):,} B"
        n /= 1024
    return f"{n:,.1f} GB"


TARGET_DEFAULTS = [
    ("volume", 100),
    ("currentCostume", 0),
    ("tempo", 60),
    ("videoTransparency", 50),
    ("videoState", "on"),
    ("textToSpeechLanguage", None),
    ("visible", True),
    ("x", 0),
    ("y", 0),
    ("size", 100),
    ("direction", 90),
    ("draggable", False),
    ("rotationStyle", "all around"),
]

MONITOR_DEFAULTS = [
    ("mode", "default"),
    ("spriteName", None),
    ("width", 0),
    ("height", 0),
    ("visible", True),
    ("sliderMin", 0),
    ("sliderMax", 100),
    ("isDiscrete", True),
]


class Options:
    def __init__(self, strip_defaults: bool = True, shorten_ids: bool = True,
                 click_to_stage: bool = False, remove_unused: bool = True,
                 compress_procs: bool = True, freq_ids: bool = True):
        self.strip_defaults = strip_defaults
        self.shorten_ids = shorten_ids
        self.click_to_stage = click_to_stage
        self.remove_unused = remove_unused
        self.compress_procs = compress_procs
        self.freq_ids = freq_ids


def default_output_path(in_path: str) -> str:
    root, ext = os.path.splitext(in_path)
    ext = ext.lower() or ".sb3"
    if ext not in (".sb3", ".json"):
        ext = ".sb3"
    return f"{root}_compressed{ext}"


class Compressor:
    """Takes a parsed project.json dict and returns a compressed dict."""

    def __init__(self, options: Options | None = None, progress=None, cancelled=None):
        self.options = options or Options()
        self.progress = progress or (lambda phase, frac, msg: None)
        self.cancelled = cancelled or (lambda: False)
        self.stats = {
            "blocks_renamed": 0,
            "vars_renamed": 0,
            "lists_renamed": 0,
            "broadcasts_renamed": 0,
            "fields_removed": 0,
            "monitors_updated": 0,
            "click_rewrites": 0,
            "vars_removed": 0,
            "lists_removed": 0,
            "procs_renamed": 0,
            "args_renamed": 0,
        }
        self.var_map: dict = {}
        self.list_map: dict = {}
        self.bc_map: dict = {}
        self.var_by_name: dict = {}
        self.list_by_name: dict = {}
        self.bc_by_name: dict = {}
        self.var_name_ids: dict = {}
        self.list_name_ids: dict = {}
        self.var_by_target: dict = {}
        self.stage_name: str | None = None
        self._used_var_ids: set = set()
        self._used_list_ids: set = set()
        self._layer_expect = 0

    def run(self, project: dict) -> dict:
        targets = project.get("targets")
        if not isinstance(targets, list) or not targets:
            raise CompressError("'targets' not found. Please provide a project.json.")

        self.progress("collect", 0.0, "Collecting variables, lists, and broadcasts...")
        self._collect(targets)
        if self.options.remove_unused:
            self.progress("collect", 1.0, "Analyzing unused variables and lists...")
            self._scan_usage(targets, project.get("monitors"))
        if self.options.shorten_ids:
            self._rename_stores(targets)
        elif self.options.remove_unused:
            self._drop_unused(targets)

        self._layer_expect = 0
        n = len(targets)
        for i, tgt in enumerate(targets):
            if self.cancelled():
                raise Cancelled()
            self.progress("targets", i / n, f"Processing target {i + 1}/{n}")
            self._process_target(tgt)
            self.progress("targets", (i + 1) / n, f"Processing target {i + 1}/{n}")

        if self.cancelled():
            raise Cancelled()
        self.progress("finalize", 0.5, "Processing monitors and metadata...")
        self._process_monitors(project)
        self._process_root(project)
        self.progress("finalize", 1.0, "Done")
        return project

    # ------------------------------------------------------------------
    def _collect(self, targets) -> None:
        vi = li = bi = 0
        total = max(len(targets), 1)
        for idx, tgt in enumerate(targets):
            if not isinstance(tgt, dict):
                continue
            tname = tgt.get("name")
            if tgt.get("isStage"):
                self.stage_name = tname
            scope = None
            if isinstance(tname, str):
                scope = self.var_by_target.setdefault(tname, {})
            for vid, ent in (tgt.get("variables") or {}).items():
                name = ent[0] if isinstance(ent, list) and ent else str(ent)
                cloud = isinstance(name, str) and name.startswith(CLOUD_PREFIX)
                base = encode_id(vi := vi + 1)
                self.var_map[vid] = ("V" + base, (CLOUD_PREFIX + " " if cloud else "") + "V" + base)
                self.var_by_name.setdefault(name, self.var_map[vid])
                self.var_name_ids.setdefault(name, set()).add(vid)
                if scope is not None:
                    scope.setdefault(name, self.var_map[vid])
            for lid, ent in (tgt.get("lists") or {}).items():
                name = ent[0] if isinstance(ent, list) and ent else str(ent)
                base = encode_id(li := li + 1)
                self.list_map[lid] = ("L" + base, "L" + base)
                self.list_by_name.setdefault(name, self.list_map[lid])
                self.list_name_ids.setdefault(name, set()).add(lid)
            for bid, ent in (tgt.get("broadcasts") or {}).items():
                name = ent[0] if isinstance(ent, list) and ent else ent
                base = encode_id(bi := bi + 1)
                self.bc_map[bid] = ("B" + base, "B" + base)
                self.bc_by_name.setdefault(name, self.bc_map[bid])
            self.progress("collect", (idx + 1) / total, "Collecting variables, lists, and broadcasts...")
        st = self.stats
        st["vars_renamed"] = len(self.var_map)
        st["lists_renamed"] = len(self.list_map)
        st["broadcasts_renamed"] = len(self.bc_map)

    # ------------------------------------------------------------------
    def _scan_usage(self, targets, monitors) -> None:
        used_v: set = set()
        used_l: set = set()

        def mark(kind, pid, name):
            used = used_v if kind == "v" else used_l
            known = self.var_map if kind == "v" else self.list_map
            by_name = self.var_name_ids if kind == "v" else self.list_name_ids
            if isinstance(pid, str) and pid in known:
                used.add(pid)
            elif name is not None:
                # The VM falls back to a name lookup when the serialized ID is
                # missing or unknown, so keep every store that name can reach.
                ids = by_name.get(name)
                if ids:
                    used.update(ids)

        def mark_unknown_field(pid):
            # Some extensions keep a store ID in a non-standard field.  If the
            # value matches a known store, keep it rather than guessing.
            if not isinstance(pid, str):
                return
            if pid in self.var_map:
                used_v.add(pid)
            elif pid in self.list_map:
                used_l.add(pid)

        def scan_input(node):
            if not isinstance(node, list):
                return
            if node and node[0] in (12, 13):
                name = node[1] if len(node) > 1 else None
                pid = node[2] if len(node) > 2 else None
                mark("v" if node[0] == 12 else "l", pid, name)
                return
            for item in node:
                scan_input(item)

        def scan_ids(node):
            # Last-resort safety net for extension blocks and unusual formats:
            # if a store ID appears anywhere in the blocks/monitors, keep it.
            if isinstance(node, dict):
                for value in node.values():
                    scan_ids(value)
            elif isinstance(node, list):
                for value in node:
                    scan_ids(value)
            elif isinstance(node, str):
                if node in self.var_map:
                    used_v.add(node)
                elif node in self.list_map:
                    used_l.add(node)

        for tgt in targets:
            if not isinstance(tgt, dict):
                continue
            scan_ids(tgt.get("blocks"))
            for blk in (tgt.get("blocks") or {}).values():
                # Standalone variable/list reporters are serialized as
                # primitive arrays instead of block objects.
                if isinstance(blk, list):
                    if blk and blk[0] in (12, 13):
                        name = blk[1] if len(blk) > 1 else None
                        pid = blk[2] if len(blk) > 2 else None
                        mark("v" if blk[0] == 12 else "l", pid, name)
                    continue
                if not isinstance(blk, dict):
                    continue
                fields = blk.get("fields")
                if isinstance(fields, dict):
                    for k, fv in fields.items():
                        if not isinstance(fv, list) or not fv:
                            continue
                        fid = fv[1] if len(fv) > 1 else None
                        if k == "VARIABLE":
                            mark("v", fid, fv[0])
                        elif k == "LIST":
                            mark("l", fid, fv[0])
                        else:
                            mark_unknown_field(fid)
                    # "sensing_of" reads a variable by name, not by ID.
                    if blk.get("opcode") == "sensing_of":
                        prop = fields.get("PROPERTY")
                        if isinstance(prop, list) and prop and prop[0] is not None:
                            ids = self.var_name_ids.get(prop[0])
                            if ids:
                                used_v.update(ids)
                inputs = blk.get("inputs")
                if isinstance(inputs, dict):
                    for value in inputs.values():
                        scan_input(value)
        for mon in monitors or []:
            if not isinstance(mon, dict):
                continue
            scan_ids(mon)
            op = mon.get("opcode")
            if op not in ("data_variable", "data_listcontents"):
                continue
            mid = mon.get("id")
            pkey = "VARIABLE" if op == "data_variable" else "LIST"
            pname = (mon.get("params") or {}).get(pkey)
            table = self.var_map if op == "data_variable" else self.list_map
            used = used_v if op == "data_variable" else used_l
            by_name = self.var_name_ids if op == "data_variable" else self.list_name_ids
            if isinstance(mid, str) and mid in table:
                used.add(mid)
            elif pname is not None:
                ids = by_name.get(pname)
                if ids:
                    used.update(ids)
        self._used_var_ids = used_v
        self._used_list_ids = used_l

    def _drop_unused(self, targets) -> None:
        """shorten_ids=False のときの元キーままの除去。"""
        st = self.stats
        for tgt in targets:
            if not isinstance(tgt, dict):
                continue
            variables = tgt.get("variables")
            if isinstance(variables, dict):
                drop = [k for k in variables if k not in self._used_var_ids]
                for k in drop:
                    del variables[k]
                st["vars_removed"] += len(drop)
            lists = tgt.get("lists")
            if isinstance(lists, dict):
                drop = [k for k in lists if k not in self._used_list_ids]
                for k in drop:
                    del lists[k]
                st["lists_removed"] += len(drop)

    def _rename_stores(self, targets) -> None:
        drop_v = self.options.remove_unused
        st = self.stats
        for tgt in targets:
            if not isinstance(tgt, dict):
                continue
            variables = tgt.get("variables")
            if isinstance(variables, dict) and variables:
                out = {}
                for k, v in variables.items():
                    m = self.var_map.get(k)
                    if m is None:
                        out[k] = v
                        continue
                    if drop_v and k not in self._used_var_ids:
                        st["vars_removed"] += 1
                        continue
                    out[m[0]] = [m[1]] + list(v[1:])
                tgt["variables"] = out
            lists = tgt.get("lists")
            if isinstance(lists, dict) and lists:
                out = {}
                for k, v in lists.items():
                    m = self.list_map.get(k)
                    if m is None:
                        out[k] = v
                        continue
                    if drop_v and k not in self._used_list_ids:
                        st["lists_removed"] += 1
                        continue
                    out[m[0]] = [m[1]] + list(v[1:])
                tgt["lists"] = out
            broadcasts = tgt.get("broadcasts")
            if isinstance(broadcasts, dict) and broadcasts:
                out = {}
                for k, v in broadcasts.items():
                    m = self.bc_map.get(k)
                    if m is None:
                        out[k] = v
                    elif isinstance(v, list):
                        out[m[0]] = [m[1]] + list(v[1:])
                    else:
                        out[m[0]] = m[1]
                tgt["broadcasts"] = out

    # ------------------------------------------------------------------
    def _process_target(self, tgt: dict) -> None:
        if not isinstance(tgt, dict):
            return
        o = self.options
        st = self.stats
        if o.strip_defaults:
            for key, dflt in TARGET_DEFAULTS:
                if key in tgt and loose_eq(tgt[key], dflt):
                    del tgt[key]
                    st["fields_removed"] += 1
            for key in ("lists", "broadcasts", "comments"):
                if key in tgt and tgt[key] == {}:
                    del tgt[key]
                    st["fields_removed"] += 1
            if "layerOrder" in tgt and loose_eq(tgt["layerOrder"], self._layer_expect):
                del tgt["layerOrder"]
                self._layer_expect += 1
                st["fields_removed"] += 1
            for cos in tgt.get("costumes") or []:
                if not isinstance(cos, dict):
                    continue
                if "bitmapResolution" in cos and loose_eq(cos["bitmapResolution"], 1):
                    del cos["bitmapResolution"]
                    st["fields_removed"] += 1
                if "md5ext" in cos:
                    del cos["md5ext"]
                    st["fields_removed"] += 1
                for key in ("rotationCenterX", "rotationCenterY"):
                    if key in cos and loose_eq(cos[key], 0):
                        del cos[key]
                        st["fields_removed"] += 1

        blocks = tgt.get("blocks")
        id_map = {}
        if o.compress_procs and isinstance(blocks, dict) and blocks:
            self._compress_procs(blocks)
        if isinstance(blocks, dict) and o.shorten_ids and blocks:
            tgt["blocks"], id_map = self._rename_blocks(blocks)
            # 注: "blocks" は sb3 スキーマで必須のため、空でも削除しない
        elif isinstance(blocks, dict) and blocks:
            self._strip_block_defaults(blocks)

        if id_map and isinstance(tgt.get("comments"), dict):
            for c in tgt["comments"].values():
                if isinstance(c, dict) and c.get("blockId") in id_map:
                    c["blockId"] = id_map[c["blockId"]]

    def _compress_procs(self, blocks: dict) -> None:
        """定義のproccode・引数名を短い名前へ置き換え、呼び出し側と引数報告ブロックを追従させる。"""
        st = self.stats
        protos = {}
        defs = []          # (hat_id, proto_id)
        calls = []
        reporters = set()
        for bid, b in blocks.items():
            if not isinstance(b, dict):
                continue
            op = b.get("opcode")
            if op == "procedures_prototype":
                protos[bid] = b
            elif op == "procedures_definition":
                cb = (b.get("inputs") or {}).get("custom_block")
                pid = cb[1] if isinstance(cb, list) and len(cb) > 1 \
                    and isinstance(cb[1], str) else None
                if pid:
                    defs.append((bid, pid))
            elif op == "procedures_call":
                calls.append(b)
            elif isinstance(op, str) and op.startswith("argument_reporter"):
                reporters.add(bid)

        if not protos or not defs:
            return

        # 旧proccodeでグループ化(重複するproccodeはバインドが曖昧なため触らない)
        groups = {}
        for hat, pid in defs:
            p = protos.get(pid)
            mut = (p or {}).get("mutation") or {}
            old = mut.get("proccode")
            if isinstance(old, str) and old:
                groups.setdefault(old, []).append((hat, pid))

        retained = {old for old, g in groups.items() if len(g) > 1}
        proc_map = {}
        argmaps = {}      # proto_id -> {old_argname: new_argname}
        used_new = set(retained)
        i = 0
        for old, grp in groups.items():
            if len(grp) > 1:
                continue
            while True:
                i += 1
                cand = encode_id(i)
                if cand not in used_new and cand != old:
                    break
            used_new.add(cand)
            proc_map[old] = cand
            st["procs_renamed"] += 1

        # 引数名の短縮(proccodeが重複している定義も各定義内では安全)
        for hat, pid in defs:
            p = protos.get(pid)
            if not p:
                continue
            mut = p.get("mutation")
            if not isinstance(mut, dict):
                continue
            old_code = mut.get("proccode")
            if old_code in proc_map:
                mut["proccode"] = proc_map[old_code]
            raw = mut.get("argumentnames")
            try:
                names = json.loads(raw) if isinstance(raw, str) else None
            except json.JSONDecodeError:
                names = None
            if not isinstance(names, list) or not names:
                continue
            new_names = [f"a{j}" for j in range(len(names))]
            amap = {o2: n2 for o2, n2 in zip(names, new_names) if o2 != n2}
            if amap:
                argmaps[pid] = amap
                st["args_renamed"] += len(amap)
            mut["argumentnames"] = json.dumps(new_names, ensure_ascii=False,
                                              separators=(",", ":"))

        for b in calls:
            mut = b.get("mutation")
            if isinstance(mut, dict) and mut.get("proccode") in proc_map:
                mut["proccode"] = proc_map[mut["proccode"]]

        # 定義配下の引数報告ブロックの参照名を更新
        for hat, pid in defs:
            amap = argmaps.get(pid)
            if not amap:
                continue
            stack = [hat]
            visited = set()
            while stack:
                cur = stack.pop()
                if cur in visited:
                    continue
                visited.add(cur)
                blk = blocks.get(cur)
                if not isinstance(blk, dict):
                    continue
                if cur in reporters:
                    fv = blk.get("fields", {}).get("VALUE")
                    if isinstance(fv, list) and fv and fv[0] in amap:
                        fv[0] = amap[fv[0]]
                inputs = blk.get("inputs")
                if isinstance(inputs, dict):
                    for v in inputs.values():
                        if isinstance(v, list):
                            for item in v[1:]:
                                if isinstance(item, str):
                                    stack.append(item)
                nxt = blk.get("next")
                if isinstance(nxt, str) and nxt:
                    stack.append(nxt)

    def _strip_block_defaults(self, blocks: dict) -> None:
        st = self.stats
        for blk in blocks.values():
            if not isinstance(blk, dict):
                continue
            if blk.get("opcode") == "event_whenthisspriteclicked" and self.options.click_to_stage:
                blk["opcode"] = "event_whenstageclicked"
                st["click_rewrites"] += 1
            if blk.get("shadow") is False:
                blk.pop("shadow", None)
                st["fields_removed"] += 1
            tl = blk.get("topLevel")
            if tl is not True and "topLevel" in blk:
                blk.pop("topLevel", None)
                st["fields_removed"] += 1
            for key in ("inputs", "fields"):
                if blk.get(key) == {}:
                    del blk[key]
                    st["fields_removed"] += 1
            # NOTE: keep "parent": null on top-level blocks. scratch-vm's
            # Blocks.getTopLevelScript() walks while parent !== null, so a
            # missing parent field (undefined) makes it index _blocks[undefined]
            # and crash when the script glows (e.g. interpreter mode in the editor).

    def _rename_blocks(self, blocks: dict) -> dict:
        o = self.options
        st = self.stats
        id_map: dict = {}
        processed = set()

        # 使用回数の事前集計(キー自身1回+参照されるごとに加算)
        counts: dict = {}
        seen: dict = {}

        def touch(key, pos):
            if key in counts:
                counts[key] += 1
            else:
                counts[key] = 1
                seen[key] = pos

        pos = 0
        for bid, blk in blocks.items():
            touch(bid, pos)
            pos += 1
            if not isinstance(blk, dict):
                continue
            inputs = blk.get("inputs")
            if isinstance(inputs, dict):
                for v in inputs.values():
                    if not isinstance(v, list):
                        continue
                    for item in v[1:]:
                        if isinstance(item, str):
                            touch(item, pos)
            nxt = blk.get("next")
            if isinstance(nxt, str) and nxt:
                touch(nxt, pos)
            par = blk.get("parent")
            if isinstance(par, str) and par:
                touch(par, pos)

        # 頻出IDほど短い純英数キーを得る
        if o.freq_ids:
            ordered = sorted(counts, key=lambda k: (-counts[k], seen[k]))
        else:
            ordered = sorted(counts, key=lambda k: seen[k])
        for i, k in enumerate(ordered):
            id_map[k] = encode_id(i + 1)
        counter = [len(ordered)]

        def nid(old: str) -> str:
            m = id_map.get(old)
            if m is None:
                counter[0] += 1
                m = encode_id(counter[0])
                id_map[old] = m
            return m

        def map_primitive(p):
            if not isinstance(p, list) or not p:
                return p
            t = p[0]
            if t == 11:
                name = p[1] if len(p) > 1 else ""
                pid = p[2] if len(p) > 2 else None
                m = self.bc_map.get(pid) if pid else None
                if m is None:
                    m = self.bc_by_name.get(name)
                if m is None:
                    return p
                if len(p) > 2:
                    return [11, m[1], m[0]] + p[3:]
                return [11, m[1]] + p[2:]
            if t in (12, 13):
                name = p[1] if len(p) > 1 else ""
                pid = p[2] if len(p) > 2 else None
                table = self.var_map if t == 12 else self.list_map
                byname = self.var_by_name if t == 12 else self.list_by_name
                m = table.get(pid) if pid else None
                if m is None:
                    m = byname.get(name)
                if m is None:
                    return p
                return [t, m[1], m[0]] + p[3:]
            return p

        def sensing_object_name(blk: dict):
            """OBJECT is normally an input pointing at sensing_of_object_menu."""
            f = (blk.get("fields") or {}).get("OBJECT")
            if isinstance(f, list) and f:
                return f[0]
            inp = (blk.get("inputs") or {}).get("OBJECT")
            if isinstance(inp, list):
                for item in inp[1:]:
                    if isinstance(item, str):
                        menu = blocks.get(item)
                        if (isinstance(menu, dict)
                                and menu.get("opcode") == "sensing_of_object_menu"):
                            mf = (menu.get("fields") or {}).get("OBJECT")
                            if isinstance(mf, list) and mf:
                                return mf[0]
            return None

        def process_from(old_start: str, reachable: bool = False) -> None:
            work = [(old_start, reachable)]
            while work:
                old, reachable = work.pop()
                if old in processed:
                    continue
                nid(old)
                blk = blocks.get(old)
                if isinstance(blk, list):
                    # Standalone primitive (e.g. a variable reporter left on
                    # the workspace): its name/ID must follow the renamed store.
                    processed.add(old)
                    blocks[old] = map_primitive(blk)
                    continue
                if not isinstance(blk, dict):
                    continue
                processed.add(old)

                # Resolve the target before input IDs are remapped below.
                sense_obj = (sensing_object_name(blk)
                             if blk.get("opcode") == "sensing_of" else None)

                if o.click_to_stage and blk.get("opcode") == "event_whenthisspriteclicked":
                    blk["opcode"] = "event_whenstageclicked"
                    st["click_rewrites"] += 1

                inputs = blk.get("inputs")
                if isinstance(inputs, dict):
                    for k, v in list(inputs.items()):
                        if not isinstance(v, list) or len(v) < 2:
                            continue
                        out = [v[0]]
                        changed = False
                        for item in v[1:]:
                            if isinstance(item, str):
                                ref = nid(item)
                                out.append(ref)
                                work.append((item, reachable))
                                changed = True
                            elif isinstance(item, list) and item and isinstance(item[0], int):
                                out.append(map_primitive(item))
                                changed = True
                            else:
                                out.append(item)
                        if changed:
                            inputs[k] = out
                    if not inputs:
                        blk.pop("inputs", None)
                        st["fields_removed"] += 1

                fields = blk.get("fields")
                if isinstance(fields, dict):
                    for k, fv in list(fields.items()):
                        if not isinstance(fv, list) or not fv:
                            continue
                        name = fv[0]
                        fid = fv[1] if len(fv) > 1 else None
                        if k == "PROPERTY" and blk.get("opcode") == "sensing_of":
                            obj_name = sense_obj
                            if obj_name == "_stage_":
                                obj_name = self.stage_name
                            if isinstance(obj_name, str):
                                if obj_name == self.stage_name:
                                    if name in SENSING_STAGE_PROPERTIES:
                                        continue
                                elif name in SENSING_SPRITE_PROPERTIES:
                                    continue
                            scope = (self.var_by_target.get(obj_name)
                                     if isinstance(obj_name, str) else None)
                            sm = scope.get(name) if scope else None
                            if sm is not None:
                                fields[k] = [sm[1]] + fv[1:]
                            continue
                        m = None
                        if k == "VARIABLE":
                            m = (self.var_map.get(fid) if fid else None) or self.var_by_name.get(name)
                        elif k == "LIST":
                            m = (self.list_map.get(fid) if fid else None) or self.list_by_name.get(name)
                        elif k == "BROADCAST_OPTION":
                            m = (self.bc_map.get(fid) if fid else None) or self.bc_by_name.get(name)
                        if m is not None:
                            fields[k] = [m[1], m[0]] + fv[2:]
                    if not fields:
                        blk.pop("fields", None)
                        st["fields_removed"] += 1

                if blk.get("shadow") is False:
                    blk.pop("shadow", None)
                    st["fields_removed"] += 1
                if blk.get("topLevel") is not True and "topLevel" in blk:
                    blk.pop("topLevel", None)
                    st["fields_removed"] += 1
                # Keep "parent": null on top-level blocks; see _strip_block_defaults.

                nxt = blk.get("next")
                if isinstance(nxt, str) and nxt:
                    blk["next"] = nid(nxt)
                    work.append((nxt, reachable))
                elif reachable:
                    # Keep an explicit null on reachable chain ends: scratch-vm's
                    # interpreter checks `nextBlockId !== null`, so a missing key
                    # (undefined) makes promise-returning blocks re-enter their
                    # stack frame. Orphan blocks are never executed, so they can
                    # keep the smaller missing-key form.
                    blk["next"] = None
                else:
                    blk.pop("next", None)

        tops = [bid for bid, blk in blocks.items()
                if isinstance(blk, dict) and blk.get("topLevel") is True]
        for top in tops:
            if self.cancelled():
                raise Cancelled()
            process_from(top, True)

        # 到達不可能なブロック(過去ツールの残骸等)も必ず改名する。
        # 残すと元の短い英数キーが生成IDと衝突し、再構築時にサイレントに
        # 上書きされてブロックが失われるため。
        for old in list(blocks.keys()):
            if self.cancelled():
                raise Cancelled()
            if old not in processed:
                process_from(old)

        for blk in blocks.values():
            if not isinstance(blk, dict):
                continue
            p = blk.get("parent")
            if isinstance(p, str) and p in id_map:
                blk["parent"] = id_map[p]
            elif p is None:
                # Keep an explicit null so Blocks.getTopLevelScript() can stop.
                blk["parent"] = None

        st["blocks_renamed"] += counter[0]
        new_blocks = {id_map.get(k, k): v for k, v in blocks.items()}
        if len(new_blocks) != len(blocks):
            raise CompressError("Internal error: block ID collision during renaming")
        return new_blocks, id_map

    # ------------------------------------------------------------------
    def _process_monitors(self, project: dict) -> None:
        mons = project.get("monitors")
        if not isinstance(mons, list):
            return
        st = self.stats
        for mon in mons:
            if not isinstance(mon, dict):
                continue
            op = mon.get("opcode")
            if self.options.shorten_ids and op in ("data_variable", "data_listcontents"):
                table = self.var_map if op == "data_variable" else self.list_map
                byname = self.var_by_name if op == "data_variable" else self.list_by_name
                pkey = "VARIABLE" if op == "data_variable" else "LIST"
                mid = mon.get("id")
                m = table.get(mid) if isinstance(mid, str) else None
                if m is None:
                    m = byname.get((mon.get("params") or {}).get(pkey))
                if m is not None:
                    mon["id"] = m[0]
                    params = mon.setdefault("params", {})
                    if pkey in params:
                        params[pkey] = m[1]
                    st["monitors_updated"] += 1
            if self.options.strip_defaults:
                mon.pop("value", None)
                for key, dflt in MONITOR_DEFAULTS:
                    if key in mon and loose_eq(mon[key], dflt):
                        del mon[key]
                        st["fields_removed"] += 1
        if not mons:
            project.pop("monitors", None)

    def _process_root(self, project: dict) -> None:
        st = self.stats
        if project.get("extensions") == []:
            del project["extensions"]
            st["fields_removed"] += 1
        meta = project.get("meta")
        if isinstance(meta, dict):
            for key in ("vm", "agent"):
                if key in meta:
                    del meta[key]
                    st["fields_removed"] += 1
            if not meta:
                del project["meta"]


# ----------------------------------------------------------------------
def load_input(in_path: str, progress=lambda p, f, m: None):
    """Load a file and return (project_dict, container, pj_raw_bytes, entries)."""
    progress("load", 0.2, f"Loading: {os.path.basename(in_path)}")
    with open(in_path, "rb") as f:
        raw = f.read()
    progress("load", 1.0, f"Loaded ({human_size(len(raw))})")

    lower = in_path.lower()
    if lower.endswith(".json"):
        entries = []
        pj_raw = raw
    elif zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            if "project.json" not in names:
                raise CompressError("project.json was not found inside the .sb3 file")
            pj_raw = zf.read("project.json")
            entries = [(i.filename, zf.read(i.filename))
                       for i in zf.infolist()
                       if i.filename != "project.json" and not i.filename.endswith("/")]
    else:
        raise CompressError("Unsupported format. Expected .sb3 or project.json (.json)")

    try:
        text = pj_raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise CompressError(f"Could not decode project.json: {e}")
    progress("parse", 0.4, "Parsing JSON...")
    try:
        project = json.loads(text)
    except json.JSONDecodeError as e:
        raise CompressError(f"JSON parse error: {e}")
    if not isinstance(project, dict):
        raise CompressError("The root of the JSON document is not an object")
    progress("parse", 1.0, f"JSON parsed ({human_size(len(pj_raw))})")
    return project, ("sb3" if entries or lower.endswith(".sb3") else "json"), pj_raw, entries


def package_sb3(entries, project_bytes: bytes, progress=lambda p, f, m: None) -> bytes:
    buf = io.BytesIO()
    total = len(entries) + 1
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for i, (name, data) in enumerate(entries):
            zf.writestr(name, data)
            progress("package", i / total, "Repacking .sb3...")
        zf.writestr("project.json", project_bytes)
    progress("package", 1.0, "Repack complete")
    return buf.getvalue()


_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def dumps_compact(project: dict) -> bytes:
    r"""ensure_ascii=False でミニファイし、単独サロゲートのみ \uXXXX エスケープする。"""
    text = json.dumps(project, ensure_ascii=False, separators=(",", ":"))
    if _SURROGATE_RE.search(text):
        text = _SURROGATE_RE.sub(lambda m: "\\u%04x" % ord(m.group()), text)
    return text.encode("utf-8")


def compress_file(in_path: str, options: Options,
                  progress=lambda p, f, m: None, cancelled=lambda: False) -> dict:
    """Run the full pipeline from input file to output bytes and return the result payload."""
    project, container, pj_raw, entries = load_input(in_path, progress)
    comp = Compressor(options, progress, cancelled)
    project = comp.run(project)

    if cancelled():
        raise Cancelled()
    progress("serialize", 0.5, "Serializing JSON...")
    out_bytes = dumps_compact(project)
    progress("serialize", 1.0, f"JSON serialized ({human_size(len(out_bytes))})")

    final = package_sb3(entries, out_bytes, progress) if container == "sb3" else out_bytes

    orig_json = len(pj_raw)
    new_json = len(out_bytes)
    ratio = (1 - new_json / orig_json) * 100 if orig_json else 0.0
    return {
        "container": container,
        "entries": entries,
        "final_bytes": final,
        "orig_json_size": orig_json,
        "new_json_size": new_json,
        "orig_file_size": os.path.getsize(in_path),
        "new_file_size": len(final),
        "ratio": ratio,
        "stats": comp.stats,
    }


# ----------------------------------------------------------------------
PROGRESS_WEIGHTS = [("load", 4), ("parse", 6), ("collect", 10), ("targets", 55),
                    ("finalize", 5), ("serialize", 10), ("package", 10)]
_PROGRESS_BASES = {}
_acc = 0
for _name, _w in PROGRESS_WEIGHTS:
    _PROGRESS_BASES[_name] = _acc
    _acc += _w


def run_cli(argv) -> int:
    if not argv:
        print("Usage: python sb3_compressor.py <input.sb3|project.json> [output]")
        print("       Run without arguments to open the GUI.")
        return 2
    in_path = argv[0]
    out_path = argv[1] if len(argv) > 1 else default_output_path(in_path)
    if not os.path.isfile(in_path):
        print(f"Error: input file not found: {in_path}")
        return 1

    state = {"pct": -1}
    last_phase = [""]

    def progress(phase, frac, msg):
        frac = min(max(float(frac), 0.0), 1.0)
        pct = _PROGRESS_BASES.get(phase, 0) + PROGRESS_WEIGHTS[-1][1]
        for name, w in PROGRESS_WEIGHTS:
            if name == phase:
                pct = _PROGRESS_BASES[name] + w * frac
                break
        if phase != last_phase[0]:
            print(f"[{phase}] {msg}")
            last_phase[0] = phase
        elif int(pct) != state["pct"]:
            state["pct"] = int(pct)
            print(f"\r  Progress {state['pct']:3d}%  {msg[:60]:<60}", end="", flush=True)

    try:
        payload = compress_file(in_path, Options(), progress)
    except CompressError as e:
        print(f"\nError: {e}")
        return 1
    except Cancelled:
        print("\nCancelled.")
        return 130
    print()

    with open(out_path, "wb") as f:
        f.write(payload["final_bytes"])
    s = payload
    print("-" * 62)
    print(f"Original project.json : {human_size(s['orig_json_size'])}")
    print(f"Compressed            : {human_size(s['new_json_size'])}  "
          f"({s['ratio']:.1f}% smaller)")
    print(f"Output file           : {out_path} ({human_size(s['new_file_size'])})")
    st = s["stats"]
    print(f"Details: blocks renamed {st['blocks_renamed']} / variables {st['vars_renamed']} / "
          f"lists {st['lists_renamed']} / broadcasts {st['broadcasts_renamed']}")
    print(f"         defaults removed {st['fields_removed']} / "
          f"unused vars/lists removed {st['vars_removed'] + st['lists_removed']} / "
          f"custom blocks shortened {st['procs_renamed']} / "
          f"monitors updated {st['monitors_updated']}")
    return 0


def run_gui() -> int:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext

    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    class App:
        def __init__(self, root: tk.Tk):
            self.root = root
            root.title("SB3 Compressor")
            root.geometry("760x680")
            root.minsize(640, 560)

            self.q: queue.Queue = queue.Queue()
            self.worker = None
            self.cancel_flag = threading.Event()
            self.payload = None
            self.in_var = tk.StringVar()
            self.out_var = tk.StringVar()
            self.opt_strip = tk.BooleanVar(value=True)
            self.opt_ids = tk.BooleanVar(value=True)
            self.opt_click = tk.BooleanVar(value=False)
            self.opt_unused = tk.BooleanVar(value=True)
            self.opt_procs = tk.BooleanVar(value=True)
            self.opt_freq = tk.BooleanVar(value=True)
            self.pct_var = tk.DoubleVar(value=0.0)
            self.phase_var = tk.StringVar(value="Idle")

            outer = ttk.Frame(root, padding=10)
            outer.pack(fill="both", expand=True)

            fin = ttk.LabelFrame(outer, text=" Input ", padding=8)
            fin.pack(fill="x")
            ttk.Label(fin, text="File:").grid(row=0, column=0, sticky="w")
            self.in_entry = ttk.Entry(fin, textvariable=self.in_var)
            self.in_entry.grid(row=0, column=1, sticky="ew", padx=4)
            ttk.Button(fin, text="Browse...", command=self.browse_input).grid(row=0, column=2)
            ttk.Label(fin, text="Supported: .sb3 / project.json (.json)",
                      foreground="#666").grid(row=1, column=1, sticky="w", padx=4)
            fin.columnconfigure(1, weight=1)

            fout = ttk.LabelFrame(outer, text=" Output (Download) ", padding=8)
            fout.pack(fill="x", pady=(8, 0))
            ttk.Label(fout, text="Save to:").grid(row=0, column=0, sticky="w")
            self.out_entry = ttk.Entry(fout, textvariable=self.out_var)
            self.out_entry.grid(row=0, column=1, sticky="ew", padx=4)
            ttk.Button(fout, text="Save As...", command=self.browse_output).grid(row=0, column=2)
            self.save_btn = ttk.Button(fout, text="Save (Download)",
                                       command=self.save_result, state="disabled")
            self.save_btn.grid(row=1, column=2, sticky="e", pady=(6, 0))
            fout.columnconfigure(1, weight=1)

            fopt = ttk.LabelFrame(outer, text=" Options ", padding=8)
            fopt.pack(fill="x", pady=(8, 0))
            ttk.Checkbutton(fopt, variable=self.opt_strip,
                            text="Strip default values (fields the VM restores)"
                            ).grid(row=0, column=0, sticky="w")
            ttk.Checkbutton(fopt, variable=self.opt_ids,
                            text="Shorten IDs (blocks, variables, lists, broadcasts)"
                            ).grid(row=1, column=0, sticky="w")
            ttk.Checkbutton(fopt, variable=self.opt_freq,
                            text="Assign the shortest keys to frequent IDs"
                            ).grid(row=2, column=0, sticky="w")
            ttk.Checkbutton(fopt, variable=self.opt_unused,
                            text="Remove unused variables and lists"
                            ).grid(row=3, column=0, sticky="w")
            ttk.Checkbutton(fopt, variable=self.opt_procs,
                            text="Shorten custom block proccodes and arguments"
                            ).grid(row=4, column=0, sticky="w")
            ttk.Checkbutton(fopt, variable=self.opt_click,
                            text="Rewrite sprite clicks as stage clicks (changes behavior)"
                            ).grid(row=5, column=0, sticky="w")

            btns = ttk.Frame(outer)
            btns.pack(fill="x", pady=8)
            self.start_btn = ttk.Button(btns, text="▶ Start Compression", command=self.start)
            self.start_btn.pack(side="left")
            self.cancel_btn = ttk.Button(btns, text="Cancel", command=self.cancel,
                                         state="disabled")
            self.cancel_btn.pack(side="left", padx=6)

            fprog = ttk.LabelFrame(outer, text=" Progress ", padding=8)
            fprog.pack(fill="x")
            self.bar = ttk.Progressbar(fprog, maximum=100.0, variable=self.pct_var)
            self.bar.pack(fill="x")
            prow = ttk.Frame(fprog)
            prow.pack(fill="x", pady=(4, 0))
            self.pct_lbl = ttk.Label(prow, text="0%")
            self.pct_lbl.pack(side="left")
            ttk.Label(prow, textvariable=self.phase_var).pack(side="left", padx=10)

            flog = ttk.LabelFrame(outer, text=" Log ", padding=8)
            flog.pack(fill="both", expand=True, pady=(8, 0))
            self.log = scrolledtext.ScrolledText(flog, height=9, state="disabled",
                                                 font=("Consolas", 9))
            self.log.pack(fill="both", expand=True)

            fres = ttk.LabelFrame(outer, text=" Result (Compression) ", padding=8)
            fres.pack(fill="x", pady=(8, 0))
            self.res_main = tk.StringVar(value="—")
            tk.Label(fres, textvariable=self.res_main,
                     font=("Segoe UI", 13, "bold"), anchor="w").pack(fill="x")
            self.res_detail = tk.StringVar(value="")
            tk.Label(fres, textvariable=self.res_detail, foreground="#444",
                     anchor="w", justify="left").pack(fill="x")

            root.protocol("WM_DELETE_WINDOW", self.on_close)
            self.poll()

        # ----------------------------------------------------------
        def log_line(self, text: str) -> None:
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            if int(self.log.index("end-1c").split(".")[0]) > 600:
                self.log.delete("1.0", "200.0")
            self.log.configure(state="disabled")

        def set_running(self, running: bool) -> None:
            self.start_btn.configure(state="disabled" if running else "normal")
            self.cancel_btn.configure(state="normal" if running else "disabled")
            self.in_entry.configure(state="disabled" if running else "normal")
            self.save_btn.configure(state="disabled")

        def browse_input(self) -> None:
            path = filedialog.askopenfilename(
                title="Select a project to compress",
                filetypes=[("Scratch projects", "*.sb3"), ("project.json", "*.json"),
                           ("All files", "*.*")])
            if path:
                self.in_var.set(path)
                self.out_var.set(default_output_path(path))
                self.payload = None
                self.res_main.set("—")
                self.res_detail.set("")
                self.pct_var.set(0)
                self.phase_var.set("Idle")
                self.save_btn.configure(state="disabled")

        def browse_output(self) -> None:
            init = self.out_var.get().strip() or default_output_path(
                self.in_var.get() or "project.sb3")
            path = filedialog.asksaveasfilename(
                title="Choose output file", initialfile=os.path.basename(init),
                initialdir=os.path.dirname(init) or ".",
                defaultextension=".sb3",
                filetypes=[("Scratch projects", "*.sb3"), ("All files", "*.*")])
            if path:
                self.out_var.set(path)

        def start(self) -> None:
            in_path = self.in_var.get().strip()
            if not in_path:
                messagebox.showwarning("SB3 Compressor", "Please select an input file.")
                return
            if not os.path.isfile(in_path):
                messagebox.showerror("SB3 Compressor", f"File not found:\n{in_path}")
                return
            opts = Options(strip_defaults=self.opt_strip.get(),
                           shorten_ids=self.opt_ids.get(),
                           click_to_stage=self.opt_click.get(),
                           remove_unused=self.opt_unused.get(),
                           compress_procs=self.opt_procs.get(),
                           freq_ids=self.opt_freq.get())
            self.payload = None
            self.cancel_flag.clear()
            self.set_running(True)
            self.pct_var.set(0)
            self.res_main.set("—")
            self.res_detail.set("")
            self.log_line("=" * 62)
            self.log_line(f"Started: {in_path}")
            t = threading.Thread(target=self.work, args=(in_path, opts), daemon=True)
            self.worker = t
            t.start()

        def cancel(self) -> None:
            self.cancel_flag.set()
            self.log_line("Cancel requested...")

        def work(self, in_path: str, opts: Options) -> None:
            q = self.q
            try:
                def prog(phase, frac, msg):
                    frac = min(max(float(frac), 0.0), 1.0)
                    pct = _PROGRESS_BASES.get(phase, 0)
                    for name, w in PROGRESS_WEIGHTS:
                        if name == phase:
                            pct = _PROGRESS_BASES[name] + w * frac
                            break
                    q.put(("prog", pct, msg))

                payload = compress_file(in_path, opts, prog, self.cancel_flag.is_set)
                q.put(("done", payload))
            except Cancelled:
                q.put(("failed", None, None))
            except CompressError as e:
                q.put(("failed", e, None))
            except Exception:
                q.put(("failed", None, traceback.format_exc()))

        def save_result(self) -> None:
            if not self.payload:
                return
            is_sb3 = self.payload["container"] == "sb3"
            init = self.out_var.get().strip() or default_output_path(
                self.in_var.get() or "project.sb3")
            if is_sb3 and not init.lower().endswith(".sb3"):
                root_, _ = os.path.splitext(init)
                init = root_ + ".sb3"
            path = filedialog.asksaveasfilename(
                title="Save (Download)", initialfile=os.path.basename(init),
                initialdir=os.path.dirname(init) or ".",
                defaultextension=".sb3" if is_sb3 else ".json",
                filetypes=[("Scratch projects", "*.sb3")] if is_sb3 else [("JSON", "*.json")])
            if not path:
                return
            try:
                with open(path, "wb") as f:
                    f.write(self.payload["final_bytes"])
            except OSError as e:
                messagebox.showerror("SB3 Compressor", f"Failed to save:\n{e}")
                return
            self.out_var.set(path)
            size = len(self.payload["final_bytes"])
            self.log_line(f"Saved: {path} ({human_size(size)})")
            messagebox.showinfo("Saved",
                                f"Saved:\n{path}\n\nSize: {human_size(size)}")

        def finish(self, payload: dict) -> None:
            self.payload = payload
            self.set_running(False)
            self.phase_var.set("Done")
            s = payload
            self.res_main.set(
                f"project.json {human_size(s['orig_json_size'])} → "
                f"{human_size(s['new_json_size'])}   ({s['ratio']:.1f}% smaller)")
            st = s["stats"]
            kind = ".sb3" if s["container"] == "sb3" else ".json"
            self.res_detail.set(
                f"Final file ({kind}): {human_size(s['new_file_size'])}\n"
                f"Blocks renamed {st['blocks_renamed']} / Variables {st['vars_renamed']} / "
                f"Lists {st['lists_renamed']} / Broadcasts {st['broadcasts_renamed']}\n"
                f"Defaults removed {st['fields_removed']} / Unused vars/lists removed "
                f"{st['vars_removed'] + st['lists_removed']} / "
                f"Custom blocks shortened {st['procs_renamed']}")
            self.log_line(f"Done: {s['ratio']:.1f}% smaller "
                          f"({human_size(s['orig_json_size'])} → "
                          f"{human_size(s['new_json_size'])})")
            if not self.out_var.get().strip():
                self.out_var.set(default_output_path(self.in_var.get()))
            self.save_btn.configure(state="normal")

        def fail(self, err, tb) -> None:
            self.set_running(False)
            self.phase_var.set("Failed")
            if tb:
                self.log_line(tb.rstrip())
                messagebox.showerror("SB3 Compressor", f"Unexpected error:\n{tb.splitlines()[-1]}")
            elif err is not None:
                self.log_line(f"Error: {err}")
                messagebox.showerror("SB3 Compressor", str(err))
            else:
                self.log_line("Cancelled.")
            self.cancel_flag.clear()

        def poll(self) -> None:
            try:
                while True:
                    msg = self.q.get_nowait()
                    kind = msg[0]
                    if kind == "prog":
                        _, pct, text = msg
                        self.pct_var.set(round(pct, 1))
                        self.pct_lbl.configure(text=f"{pct:.0f}%")
                        self.phase_var.set(text)
                    elif kind == "done":
                        self.finish(msg[1])
                    elif kind == "failed":
                        self.fail(msg[1], msg[2])
            except queue.Empty:
                pass
            self.root.after(60, self.poll)

        def on_close(self) -> None:
            if self.worker and self.worker.is_alive():
                if not messagebox.askokcancel("Exit", "Compression is still running. Exit anyway?"):
                    return
                self.cancel_flag.set()
            self.root.destroy()

    root = tk.Tk()
    app = App(root)
    autoclose = os.environ.get("SB3C_AUTOCLOSE")
    if autoclose:
        root.after(max(int(autoclose), 0), root.destroy)
    root.mainloop()
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if argv:
        return run_cli(argv)
    return run_gui()


if __name__ == "__main__":
    sys.exit(main())

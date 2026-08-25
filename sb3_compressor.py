#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SB3 Compressor - Scratch (TurboWarp) プロジェクト .sb3 の project.json を可逆圧縮するツール。

Scratch作品「sb3 Compressor」の Python 移植版。
  - ブロックID / 変数・リスト・放送の名前を短いIDへ一括改名
  - VMが補完できるデフォルト値フィールドを削除
  - JSONをミニファイし、assetsをそのまま同梱して .sb3 を再パック

使い方:
  python sb3_compressor.py                -> GUI 起動
  python sb3_compressor.py in.sb3 [out]   -> CLI モード
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
                 click_to_stage: bool = False):
        self.strip_defaults = strip_defaults
        self.shorten_ids = shorten_ids
        self.click_to_stage = click_to_stage


def default_output_path(in_path: str) -> str:
    root, ext = os.path.splitext(in_path)
    ext = ext.lower() or ".sb3"
    if ext not in (".sb3", ".json"):
        ext = ".sb3"
    return f"{root}_compressed{ext}"


class Compressor:
    """project.json (dict) を受け取り、圧縮済み dict を返す。"""

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
        }
        self.var_map: dict = {}
        self.list_map: dict = {}
        self.bc_map: dict = {}
        self.var_by_name: dict = {}
        self.list_by_name: dict = {}
        self.bc_by_name: dict = {}
        self._layer_expect = 0

    def run(self, project: dict) -> dict:
        targets = project.get("targets")
        if not isinstance(targets, list) or not targets:
            raise CompressError("'targets' が見つかりません。project.json を入力してください")

        self.progress("collect", 0.0, "変数・リスト・放送を収集中…")
        self._collect(targets)
        if self.options.shorten_ids:
            self._rename_stores(targets)

        self._layer_expect = 0
        n = len(targets)
        for i, tgt in enumerate(targets):
            if self.cancelled():
                raise Cancelled()
            self.progress("targets", i / n, f"ターゲット処理中 {i + 1}/{n}")
            self._process_target(tgt)
            self.progress("targets", (i + 1) / n, f"ターゲット処理中 {i + 1}/{n}")

        if self.cancelled():
            raise Cancelled()
        self.progress("finalize", 0.5, "モニター・メタ情報処理中…")
        self._process_monitors(project)
        self._process_root(project)
        self.progress("finalize", 1.0, "完了")
        return project

    # ------------------------------------------------------------------
    def _collect(self, targets) -> None:
        vi = li = bi = 0
        total = max(len(targets), 1)
        for idx, tgt in enumerate(targets):
            if not isinstance(tgt, dict):
                continue
            for vid, ent in (tgt.get("variables") or {}).items():
                name = ent[0] if isinstance(ent, list) and ent else str(ent)
                cloud = isinstance(name, str) and name.startswith(CLOUD_PREFIX)
                base = encode_id(vi := vi + 1)
                self.var_map[vid] = ("V" + base, (CLOUD_PREFIX + " " if cloud else "") + "V" + base)
                self.var_by_name.setdefault(name, self.var_map[vid])
            for lid, ent in (tgt.get("lists") or {}).items():
                name = ent[0] if isinstance(ent, list) and ent else str(ent)
                base = encode_id(li := li + 1)
                self.list_map[lid] = ("L" + base, "L" + base)
                self.list_by_name.setdefault(name, self.list_map[lid])
            for bid, ent in (tgt.get("broadcasts") or {}).items():
                name = ent[0] if isinstance(ent, list) and ent else ent
                base = encode_id(bi := bi + 1)
                self.bc_map[bid] = ("B" + base, "B" + base)
                self.bc_by_name.setdefault(name, self.bc_map[bid])
            self.progress("collect", (idx + 1) / total, "変数・リスト・放送を収集中…")
        st = self.stats
        st["vars_renamed"] = len(self.var_map)
        st["lists_renamed"] = len(self.list_map)
        st["broadcasts_renamed"] = len(self.bc_map)

    def _rename_stores(self, targets) -> None:
        for tgt in targets:
            if not isinstance(tgt, dict):
                continue
            variables = tgt.get("variables")
            if isinstance(variables, dict) and variables:
                tgt["variables"] = {
                    self.var_map[k][0]:
                        [self.var_map[k][1]] + list(v[1:]) if k in self.var_map else v
                    for k, v in variables.items()
                }
            lists = tgt.get("lists")
            if isinstance(lists, dict) and lists:
                tgt["lists"] = {
                    self.list_map[k][0]:
                        [self.list_map[k][1]] + list(v[1:]) if k in self.list_map else v
                    for k, v in lists.items()
                }
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
        if isinstance(blocks, dict) and o.shorten_ids and blocks:
            tgt["blocks"], id_map = self._rename_blocks(blocks)
            # 注: "blocks" は sb3 スキーマで必須のため、空でも削除しない
        elif isinstance(blocks, dict) and blocks:
            self._strip_block_defaults(blocks)

        if id_map and isinstance(tgt.get("comments"), dict):
            for c in tgt["comments"].values():
                if isinstance(c, dict) and c.get("blockId") in id_map:
                    c["blockId"] = id_map[c["blockId"]]

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
            if blk.get("parent") is None:
                del blk["parent"]

    def _rename_blocks(self, blocks: dict) -> dict:
        o = self.options
        st = self.stats
        id_map: dict = {}
        counter = [0]
        processed = set()

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

        def process_from(old_start: str) -> None:
            work = [old_start]
            while work:
                old = work.pop()
                if old in processed:
                    continue
                nid(old)
                blk = blocks.get(old)
                if not isinstance(blk, dict):
                    continue
                processed.add(old)

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
                                work.append(item)
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
                if blk.get("parent") is None:
                    blk.pop("parent", None)

                nxt = blk.get("next")
                if isinstance(nxt, str) and nxt:
                    blk["next"] = nid(nxt)
                    work.append(nxt)
                else:
                    blk.pop("next", None)

        tops = [bid for bid, blk in blocks.items()
                if isinstance(blk, dict) and blk.get("topLevel") is True]
        for top in tops:
            if self.cancelled():
                raise Cancelled()
            process_from(top)

        # 到達不可能なブロック(過去ツールの残骸等)も必ず改名する。
        # 残すと元の短い英数キーが生成IDと衝突し、再構築時にサイレントに
        # 上書きされてブロックが失われるため。
        for old in list(blocks.keys()):
            if self.cancelled():
                raise Cancelled()
            if old not in processed:
                process_from(old)

        for old, blk in blocks.items():
            if isinstance(blk, dict) and "parent" in blk:
                p = blk["parent"]
                if p is None:
                    del blk["parent"]
                elif isinstance(p, str) and p in id_map:
                    blk["parent"] = id_map[p]

        st["blocks_renamed"] += counter[0]
        new_blocks = {id_map.get(k, k): v for k, v in blocks.items()}
        if len(new_blocks) != len(blocks):
            raise CompressError("内部エラー: ブロックID改名で衝突が発生しました")
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
    """ファイルを読み、(project_dict, container, pj_raw_bytes, entries) を返す。"""
    progress("load", 0.2, f"読み込み中: {os.path.basename(in_path)}")
    with open(in_path, "rb") as f:
        raw = f.read()
    progress("load", 1.0, f"読み込み完了 ({human_size(len(raw))})")

    lower = in_path.lower()
    if lower.endswith(".json"):
        entries = []
        pj_raw = raw
    elif zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            if "project.json" not in names:
                raise CompressError(".sb3 内に project.json が見つかりません")
            pj_raw = zf.read("project.json")
            entries = [(i.filename, zf.read(i.filename))
                       for i in zf.infolist()
                       if i.filename != "project.json" and not i.filename.endswith("/")]
    else:
        raise CompressError("対応形式は .sb3 または project.json (.json) です")

    try:
        text = pj_raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise CompressError(f"project.json の文字コードを読めません: {e}")
    progress("parse", 0.4, "JSON解析中…")
    try:
        project = json.loads(text)
    except json.JSONDecodeError as e:
        raise CompressError(f"JSON解析エラー: {e}")
    if not isinstance(project, dict):
        raise CompressError("JSONのルートがオブジェクトではありません")
    progress("parse", 1.0, f"JSON解析完了 ({human_size(len(pj_raw))})")
    return project, ("sb3" if entries or lower.endswith(".sb3") else "json"), pj_raw, entries


def package_sb3(entries, project_bytes: bytes, progress=lambda p, f, m: None) -> bytes:
    buf = io.BytesIO()
    total = len(entries) + 1
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for i, (name, data) in enumerate(entries):
            zf.writestr(name, data)
            progress("package", i / total, "SB3再パック中…")
        zf.writestr("project.json", project_bytes)
    progress("package", 1.0, "SB3再パック完了")
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
    """入力ファイルから最終出力バイト列まで一括処理し、結果payloadを返す。"""
    project, container, pj_raw, entries = load_input(in_path, progress)
    comp = Compressor(options, progress, cancelled)
    project = comp.run(project)

    if cancelled():
        raise Cancelled()
    progress("serialize", 0.5, "JSON生成中…")
    out_bytes = dumps_compact(project)
    progress("serialize", 1.0, f"JSON生成完了 ({human_size(len(out_bytes))})")

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
        print("使い方: python sb3_compressor.py <入力.sb3|project.json> [出力先]")
        print("       引数なしで起動するとGUIが開きます")
        return 2
    in_path = argv[0]
    out_path = argv[1] if len(argv) > 1 else default_output_path(in_path)
    if not os.path.isfile(in_path):
        print(f"エラー: 入力ファイルが見つかりません: {in_path}")
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
            print(f"\r  進捗 {state['pct']:3d}%  {msg[:60]:<60}", end="", flush=True)

    try:
        payload = compress_file(in_path, Options(), progress)
    except CompressError as e:
        print(f"\nエラー: {e}")
        return 1
    except Cancelled:
        print("\n中止しました")
        return 130
    print()

    with open(out_path, "wb") as f:
        f.write(payload["final_bytes"])
    s = payload
    print("-" * 62)
    print(f"元 project.json : {human_size(s['orig_json_size'])}")
    print(f"圧縮後          : {human_size(s['new_json_size'])}  "
          f"(圧縮率 {s['ratio']:.1f}% 削減)")
    print(f"最終ファイル    : {out_path} ({human_size(s['new_file_size'])})")
    st = s["stats"]
    print(f"内訳: ブロックID改名 {st['blocks_renamed']} / 変数 {st['vars_renamed']} / "
          f"リスト {st['lists_renamed']} / 放送 {st['broadcasts_renamed']}")
    print(f"      既定値削除 {st['fields_removed']} / モニター更新 {st['monitors_updated']}")
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
            self.pct_var = tk.DoubleVar(value=0.0)
            self.phase_var = tk.StringVar(value="待機中")

            outer = ttk.Frame(root, padding=10)
            outer.pack(fill="both", expand=True)

            fin = ttk.LabelFrame(outer, text=" 入力 ", padding=8)
            fin.pack(fill="x")
            ttk.Label(fin, text="ファイル:").grid(row=0, column=0, sticky="w")
            self.in_entry = ttk.Entry(fin, textvariable=self.in_var)
            self.in_entry.grid(row=0, column=1, sticky="ew", padx=4)
            ttk.Button(fin, text="参照…", command=self.browse_input).grid(row=0, column=2)
            ttk.Label(fin, text="対応形式: .sb3 / project.json (.json)",
                      foreground="#666").grid(row=1, column=1, sticky="w", padx=4)
            fin.columnconfigure(1, weight=1)

            fout = ttk.LabelFrame(outer, text=" 出力（ダウンロード） ", padding=8)
            fout.pack(fill="x", pady=(8, 0))
            ttk.Label(fout, text="保存先:").grid(row=0, column=0, sticky="w")
            self.out_entry = ttk.Entry(fout, textvariable=self.out_var)
            self.out_entry.grid(row=0, column=1, sticky="ew", padx=4)
            ttk.Button(fout, text="保存先…", command=self.browse_output).grid(row=0, column=2)
            self.save_btn = ttk.Button(fout, text="保存（ダウンロード）",
                                       command=self.save_result, state="disabled")
            self.save_btn.grid(row=1, column=2, sticky="e", pady=(6, 0))
            fout.columnconfigure(1, weight=1)

            fopt = ttk.LabelFrame(outer, text=" オプション ", padding=8)
            fopt.pack(fill="x", pady=(8, 0))
            ttk.Checkbutton(fopt, variable=self.opt_strip,
                            text="デフォルト値の削除（VMが補完するフィールドを除去）"
                            ).grid(row=0, column=0, sticky="w")
            ttk.Checkbutton(fopt, variable=self.opt_ids,
                            text="ID短縮（ブロックID・変数/リスト/放送の名前を短く改名）"
                            ).grid(row=1, column=0, sticky="w")
            ttk.Checkbutton(fopt, variable=self.opt_click,
                            text="スプライトクリック→ステージクリックに書き換え（非推奨：挙動が変わります）"
                            ).grid(row=2, column=0, sticky="w")

            btns = ttk.Frame(outer)
            btns.pack(fill="x", pady=8)
            self.start_btn = ttk.Button(btns, text="▶ 圧縮開始", command=self.start)
            self.start_btn.pack(side="left")
            self.cancel_btn = ttk.Button(btns, text="中止", command=self.cancel,
                                         state="disabled")
            self.cancel_btn.pack(side="left", padx=6)

            fprog = ttk.LabelFrame(outer, text=" 進捗 ", padding=8)
            fprog.pack(fill="x")
            self.bar = ttk.Progressbar(fprog, maximum=100.0, variable=self.pct_var)
            self.bar.pack(fill="x")
            prow = ttk.Frame(fprog)
            prow.pack(fill="x", pady=(4, 0))
            self.pct_lbl = ttk.Label(prow, text="0%")
            self.pct_lbl.pack(side="left")
            ttk.Label(prow, textvariable=self.phase_var).pack(side="left", padx=10)

            flog = ttk.LabelFrame(outer, text=" ログ ", padding=8)
            flog.pack(fill="both", expand=True, pady=(8, 0))
            self.log = scrolledtext.ScrolledText(flog, height=9, state="disabled",
                                                 font=("Consolas", 9))
            self.log.pack(fill="both", expand=True)

            fres = ttk.LabelFrame(outer, text=" 結果（圧縮率） ", padding=8)
            fres.pack(fill="x", pady=(8, 0))
            self.res_main = tk.StringVar(value="―")
            tk.Label(fres, textvariable=self.res_main,
                     font=("Meiryo UI", 13, "bold"), anchor="w").pack(fill="x")
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
                title="圧縮するプロジェクトを選択",
                filetypes=[("Scratchプロジェクト", "*.sb3"), ("project.json", "*.json"),
                           ("すべてのファイル", "*.*")])
            if path:
                self.in_var.set(path)
                self.out_var.set(default_output_path(path))
                self.payload = None
                self.res_main.set("―")
                self.res_detail.set("")
                self.pct_var.set(0)
                self.phase_var.set("待機中")
                self.save_btn.configure(state="disabled")

        def browse_output(self) -> None:
            init = self.out_var.get().strip() or default_output_path(
                self.in_var.get() or "project.sb3")
            path = filedialog.asksaveasfilename(
                title="保存先を選択", initialfile=os.path.basename(init),
                initialdir=os.path.dirname(init) or ".",
                defaultextension=".sb3",
                filetypes=[("Scratchプロジェクト", "*.sb3"), ("すべてのファイル", "*.*")])
            if path:
                self.out_var.set(path)

        def start(self) -> None:
            in_path = self.in_var.get().strip()
            if not in_path:
                messagebox.showwarning("SB3 Compressor", "入力ファイルを選択してください")
                return
            if not os.path.isfile(in_path):
                messagebox.showerror("SB3 Compressor", f"ファイルが見つかりません:\n{in_path}")
                return
            opts = Options(strip_defaults=self.opt_strip.get(),
                           shorten_ids=self.opt_ids.get(),
                           click_to_stage=self.opt_click.get())
            self.payload = None
            self.cancel_flag.clear()
            self.set_running(True)
            self.pct_var.set(0)
            self.res_main.set("―")
            self.res_detail.set("")
            self.log_line("=" * 62)
            self.log_line(f"開始: {in_path}")
            t = threading.Thread(target=self.work, args=(in_path, opts), daemon=True)
            self.worker = t
            t.start()

        def cancel(self) -> None:
            self.cancel_flag.set()
            self.log_line("中止要求…")

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
                title="保存（ダウンロード）", initialfile=os.path.basename(init),
                initialdir=os.path.dirname(init) or ".",
                defaultextension=".sb3" if is_sb3 else ".json",
                filetypes=[("Scratchプロジェクト", "*.sb3")] if is_sb3 else [("JSON", "*.json")])
            if not path:
                return
            try:
                with open(path, "wb") as f:
                    f.write(self.payload["final_bytes"])
            except OSError as e:
                messagebox.showerror("SB3 Compressor", f"保存に失敗しました:\n{e}")
                return
            self.out_var.set(path)
            size = len(self.payload["final_bytes"])
            self.log_line(f"保存完了: {path} ({human_size(size)})")
            messagebox.showinfo("保存完了",
                                f"保存しました:\n{path}\n\nサイズ: {human_size(size)}")

        def finish(self, payload: dict) -> None:
            self.payload = payload
            self.set_running(False)
            self.phase_var.set("完了")
            s = payload
            self.res_main.set(
                f"project.json {human_size(s['orig_json_size'])} → "
                f"{human_size(s['new_json_size'])}   （{s['ratio']:.1f}% 削減）")
            st = s["stats"]
            kind = ".sb3" if s["container"] == "sb3" else ".json"
            self.res_detail.set(
                f"最終ファイル{kind}: {human_size(s['new_file_size'])}   |   "
                f"ブロックID改名 {st['blocks_renamed']} / 変数 {st['vars_renamed']} / "
                f"リスト {st['lists_renamed']} / 放送 {st['broadcasts_renamed']} / "
                f"既定値削除 {st['fields_removed']}")
            self.log_line(f"完了: 圧縮率 {s['ratio']:.1f}% 削減 "
                          f"({human_size(s['orig_json_size'])} → "
                          f"{human_size(s['new_json_size'])})")
            if not self.out_var.get().strip():
                self.out_var.set(default_output_path(self.in_var.get()))
            self.save_btn.configure(state="normal")

        def fail(self, err, tb) -> None:
            self.set_running(False)
            self.phase_var.set("失敗")
            if tb:
                self.log_line(tb.rstrip())
                messagebox.showerror("SB3 Compressor", f"予期しないエラーが発生しました:\n{tb.splitlines()[-1]}")
            elif err is not None:
                self.log_line(f"エラー: {err}")
                messagebox.showerror("SB3 Compressor", str(err))
            else:
                self.log_line("中止しました")
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
                if not messagebox.askokcancel("終了", "圧縮中ですが終了しますか？"):
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

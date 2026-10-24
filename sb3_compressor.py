#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SB3 Compressor - behavior-preserving compressor for Scratch (TurboWarp) .sb3 project files.

Python port of the Scratch project "sb3 Compressor".
  - Rename block IDs and variable/list/broadcast names to short IDs
  - Remove variables/lists that are never displayed, written, or read
  - Blank initial values that are always overwritten before the first read
  - Remove unreachable blocks/comments, unused definitions and broadcasts
  - Drop input defaults hidden under covering reporter blocks
  - Fold numeric-only reporter expressions (JavaScript number semantics)
  - Inline single-use non-warp definitions and drop no-op definitions/messages
  - Turn empty if/else blocks into plain if blocks
  - Replace consecutive identical block groups with repeat loops
  - Propagate variables that never change into their read sites
  - Extract repeated code into custom-block definitions
  - Extract near-duplicate blocks whose only differences are literals
  - Shorten custom block proccodes and argument names
  - Remove default-valued fields that the VM reconstructs
  - Minify JSON and repack the .sb3 with its assets unchanged

Usage:
  python sb3_compressor.py                -> launch the GUI
  python sb3_compressor.py in.sb3 [out]   -> CLI mode
"""

from __future__ import annotations

import copy
import io
import json
import math
import os
import queue
import re
import sys
import threading
import traceback
import zipfile
from collections import deque

CLOUD_PREFIX = "\u2601"

# Stores/blocks used by the analysis passes below.
VAR_WRITE_OPS = {"data_setvariableto", "data_changevariableby", "control_for_each"}
VAR_READ_OPS = {"data_variable"}
LIST_READ_OPS = {"data_listcontents", "data_itemoflist", "data_itemnumoflist",
                 "data_lengthoflist", "data_listcontainsitem"}
LIST_WRITE_OPS = {"data_addtolist", "data_deleteoflist", "data_deletealloflist",
                  "data_insertatlist", "data_replaceitemoflist"}
DATA_REPORTER_OPS = {"data_variable", "data_listcontents", "data_itemoflist",
                     "data_itemnumoflist", "data_lengthoflist",
                     "data_listcontainsitem"}
# Top-level blocks with these opcodes are executable stacks. A loose copy on
# the workspace is unreachable; a top-level reporter is kept as workspace data.
LOOSE_STACK_OPS = {
    "event_broadcast", "event_broadcastandwait", "procedures_call",
    "procedures_prototype", "control_stop", "control_wait",
    "control_wait_until", "control_create_clone_of", "control_delete_this_clone",
    "control_stop_other_scripts",
    "data_setvariableto", "data_changevariableby", "data_showvariable",
    "data_hidevariable", "data_showlist", "data_hidelist",
    "data_addtolist", "data_deleteoflist", "data_deletealloflist",
    "data_insertatlist", "data_replaceitemoflist",
}
SENSING_STACK_OPS = {"sensing_askandwait", "sensing_setdragmode",
                     "sensing_resettimer"}
EXTRACT_EXCLUDE_OPS = {
    "procedures_definition", "procedures_prototype",
    "argument_reporter_string_number", "argument_reporter_boolean",
    "control_stop", "procedures_return",
}
# Blocks that make a candidate unextractable even when they are only part of
# a larger chain.  Argument reporters are handled separately: they can be
# turned into parameters of the generated custom block.
EXTRACT_FORBIDDEN_OPS = {
    "procedures_definition", "procedures_prototype", "control_stop",
    "procedures_return",
}
# Primitive input types that hold literal text/numbers.  A difference in one
# of these slots can be passed through a custom-block argument and therefore
# can be shared by a near-duplicate definition.
LITERAL_PRIMITIVE_TYPES = {4, 5, 6, 7, 8, 10}


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


def proccode_placeholders(code: str) -> list[str]:
    """Return the ``%s``/``%b`` placeholders of a custom-block proccode.

    Renaming a proccode must keep every placeholder, otherwise the prototype
    declares arguments that the label does not contain and Scratch can no
    longer bind the block's input slots.  ``%%`` is an escaped literal percent.
    """
    out = []
    i = 0
    while i < len(code):
        if code[i] == "%" and i + 1 < len(code):
            nxt = code[i + 1]
            if nxt == "%":
                i += 2
                continue
            if nxt in ("s", "b"):
                out.append("%" + nxt)
                i += 2
                continue
        i += 1
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


def js_to_number(value) -> float:
    """Approximate Scratch's ``Cast.toNumber`` (JavaScript ``Number``).

    Anything JavaScript turns into ``NaN`` becomes ``0`` here, exactly like
    the VM.  Unlike Python's ``float``, ``Number`` does not accept ``inf``,
    ``nan`` or underscore separators, so those are rejected explicitly.
    """
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        try:
            out = float(value)
        except (TypeError, OverflowError):
            return 0.0
        return 0.0 if math.isnan(out) else out
    try:
        text = str(value).strip()
    except Exception:
        return 0.0
    if not text:
        return 0.0
    if text in ("Infinity", "+Infinity"):
        return float("inf")
    if text == "-Infinity":
        return float("-inf")
    low = text.lower()
    if "nan" in low or "inf" in low or "_" in text:
        return 0.0
    if len(text) > 2 and text[0] == "0" and text[1].lower() in "xob":
        try:
            return float(int(text, 0))
        except (ValueError, OverflowError):
            return 0.0
    try:
        out = float(text)
    except (ValueError, OverflowError):
        return 0.0
    return 0.0 if math.isnan(out) else out


def js_number_str(value: float) -> str | None:
    """Serialize a number the way JavaScript would, preserving -0/Infinity."""
    if isinstance(value, bool):
        value = float(value)
    if not isinstance(value, (int, float)):
        return None
    value = float(value)
    if math.isnan(value):
        return None
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    if value == 0.0:
        return "-0" if math.copysign(1.0, value) < 0 else "0"
    candidates = []
    try:
        candidates.append(str(int(value)))
    except (ValueError, OverflowError):
        pass
    candidates.append(repr(value))
    best = None
    for text in candidates:
        if text.endswith(".0"):
            text = text[:-2]
        # Shorten exponents ("1e-07" -> "1e-7"); both parse identically.
        text = re.sub(r"e([+-])0+(\d)", r"e\1\2", text)
        try:
            parsed = float(text)
        except (ValueError, OverflowError):
            continue
        if parsed != value or math.copysign(1.0, parsed) != math.copysign(1.0, value):
            continue
        if best is None or len(text) < len(best):
            best = text
    return best


def js_round(value: float) -> float:
    """JavaScript ``Math.round`` (ties go towards +Infinity, -0 preserved)."""
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        return value
    result = math.floor(value + 0.5)
    if result == 0 and math.copysign(1.0, value) < 0:
        return -0.0
    return float(result)


def js_floor(value: float) -> float:
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        return value
    result = math.floor(value)
    if result == 0 and math.copysign(1.0, value) < 0:
        return -0.0
    return float(result)


def js_ceil(value: float) -> float:
    value = float(value)
    if math.isnan(value) or math.isinf(value):
        return value
    result = math.ceil(value)
    if result == 0 and math.copysign(1.0, value) < 0:
        return -0.0
    return float(result)


def js_divide(left: float, right: float) -> float:
    """JavaScript division: no exception, ``x/0`` becomes ±Infinity/NaN."""
    try:
        return left / right
    except ZeroDivisionError:
        if left == 0 or math.isnan(left):
            return float("nan")
        sign = math.copysign(1.0, left) * math.copysign(1.0, right)
        return float("inf") if sign > 0 else float("-inf")
    except OverflowError:
        sign = math.copysign(1.0, left) * math.copysign(1.0, right)
        return float("inf") if sign > 0 else float("-inf")


def js_mod(left: float, right: float) -> float:
    """Scratch's ``mod`` (JavaScript remainder, then floored to the divisor)."""
    try:
        result = math.fmod(left, right)
    except (ValueError, ZeroDivisionError):
        return float("nan")
    if math.isnan(result):
        return result
    try:
        if result / right < 0:
            result += right
    except ZeroDivisionError:
        pass
    return result


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
                 compress_procs: bool = True, freq_ids: bool = True,
                 drop_obscured_shadows: bool = True,
                 remove_unreachable: bool = True,
                 clear_initial_values: bool = True,
                 extract_duplicates: bool = True,
                 near_duplicates: bool = True,
                 simplify_if_else: bool = True,
                 remove_noops: bool = True,
                 inline_single_call: bool = True,
                 fold_constants: bool = True,
                 loop_duplicates: bool = True,
                 propagate_constants: bool = True):
        self.strip_defaults = strip_defaults
        self.shorten_ids = shorten_ids
        self.click_to_stage = click_to_stage
        self.remove_unused = remove_unused
        self.compress_procs = compress_procs
        self.freq_ids = freq_ids
        self.drop_obscured_shadows = drop_obscured_shadows
        self.remove_unreachable = remove_unreachable
        self.clear_initial_values = clear_initial_values
        self.extract_duplicates = extract_duplicates
        self.near_duplicates = near_duplicates
        self.simplify_if_else = simplify_if_else
        self.remove_noops = remove_noops
        self.inline_single_call = inline_single_call
        self.fold_constants = fold_constants
        self.loop_duplicates = loop_duplicates
        self.propagate_constants = propagate_constants


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
            "obscured_shadows_removed": 0,
            "unreachable_blocks_removed": 0,
            "unreachable_comments_removed": 0,
            "broadcasts_removed": 0,
            "procs_removed": 0,
            "vars_initialized": 0,
            "lists_initialized": 0,
            "duplicates_extracted": 0,
            "dup_blocks_saved": 0,
            "near_duplicates_extracted": 0,
            "near_blocks_saved": 0,
            "ifelse_converted": 0,
            "noop_procs_removed": 0,
            "noop_calls_removed": 0,
            "noop_receivers_removed": 0,
            "noop_broadcasts_removed": 0,
            "noop_messages_removed": 0,
            "procs_inlined": 0,
            "const_values_folded": 0,
            "loops_created": 0,
            "loop_blocks_saved": 0,
            "const_vars_inlined": 0,
            "const_reads_inlined": 0,
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
        self.var_orig_name: dict = {}
        self.list_orig_name: dict = {}
        self.var_cloud_ids: set = set()
        self.stage_name: str | None = None
        self._used_var_ids: set = set()
        self._used_list_ids: set = set()
        self._dropped_var_ids: set = set()
        self._dropped_list_ids: set = set()
        self._read_var_ids: set = set()
        self._read_list_ids: set = set()
        self._write_var_ids: set = set()
        self._write_list_ids: set = set()
        self._show_var_ids: set = set()
        self._show_list_ids: set = set()
        self._visible_var_ids: set = set()
        self._visible_list_ids: set = set()
        self._standalone_var_ids: set = set()
        self._standalone_list_ids: set = set()
        self._sensed_var_ids: set = set()
        self._display_var_ids: set = set()
        self._display_list_ids: set = set()
        self._layer_expect = 0

    def run(self, project: dict) -> dict:
        targets = project.get("targets")
        if not isinstance(targets, list) or not targets:
            raise CompressError("'targets' not found. Please provide a project.json.")

        self.progress("collect", 0.0, "Collecting variables, lists, and broadcasts...")
        if self.options.drop_obscured_shadows:
            self._drop_obscured_shadows(targets)
        if self.options.remove_unreachable:
            self.progress("collect", 1.0, "Removing unreachable blocks and comments...")
            self._remove_unreachable(project)

        self._collect(targets)
        # Usage data is also needed by the initial-value and display analyses.
        self.progress("collect", 1.0, "Analyzing variables, lists, and monitors...")
        self._scan_usage(targets, project.get("monitors"))
        if not self.options.remove_unused:
            self._used_var_ids = set(self.var_map)
            self._used_list_ids = set(self.list_map)
            self._dropped_var_ids = set()
            self._dropped_list_ids = set()
        else:
            self._dropped_var_ids = set(self.var_map) - self._used_var_ids
            self._dropped_list_ids = set(self.list_map) - self._used_list_ids

        if self.options.clear_initial_values:
            self.progress("collect", 1.0, "Analyzing initial values...")
            self._clear_initial_values(targets)

        if (self.options.simplify_if_else or self.options.remove_noops
                or self.options.inline_single_call
                or self.options.fold_constants
                or self.options.loop_duplicates
                or self.options.propagate_constants):
            self.progress("collect", 1.0, "Simplifying scripts...")
            self._simplify_project(project)

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
                self.var_orig_name[vid] = name
                if cloud:
                    self.var_cloud_ids.add(vid)
                base = encode_id(vi := vi + 1)
                self.var_map[vid] = ("V" + base, (CLOUD_PREFIX + " " if cloud else "") + "V" + base)
                self.var_by_name.setdefault(name, self.var_map[vid])
                self.var_name_ids.setdefault(name, set()).add(vid)
                if scope is not None:
                    scope.setdefault(name, self.var_map[vid])
            for lid, ent in (tgt.get("lists") or {}).items():
                name = ent[0] if isinstance(ent, list) and ent else str(ent)
                self.list_orig_name[lid] = name
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
        read_v: set = set()
        read_l: set = set()
        write_v: set = set()
        write_l: set = set()
        show_v: set = set()
        show_l: set = set()
        visible_v: set = set()
        visible_l: set = set()
        standalone_v: set = set()
        standalone_l: set = set()
        sensed_v: set = set()
        unknown_read_v: set = set()
        unknown_read_l: set = set()

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
                read_v.add(pid)
                unknown_read_v.add(pid)
            elif pid in self.list_map:
                used_l.add(pid)
                read_l.add(pid)
                unknown_read_l.add(pid)

        def mark_read(kind, pid, name):
            table = self.var_map if kind == "v" else self.list_map
            by_name = self.var_name_ids if kind == "v" else self.list_name_ids
            out = read_v if kind == "v" else read_l
            if isinstance(pid, str) and pid in table:
                out.add(pid)
            elif name is not None:
                out.update(by_name.get(name, set()))

        def scan_input(node):
            if not isinstance(node, list):
                return
            if node and node[0] in (12, 13):
                name = node[1] if len(node) > 1 else None
                pid = node[2] if len(node) > 2 else None
                kind = "v" if node[0] == 12 else "l"
                mark(kind, pid, name)
                mark_read(kind, pid, name)
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
                        kind = "v" if blk[0] == 12 else "l"
                        mark(kind, pid, name)
                        (standalone_v if kind == "v" else standalone_l).update(
                            [pid] if isinstance(pid, str) and pid in
                            (self.var_map if kind == "v" else self.list_map)
                            else (self.var_name_ids if kind == "v"
                                  else self.list_name_ids).get(name, set()))
                    continue
                if not isinstance(blk, dict):
                    continue
                op = blk.get("opcode")
                fields = blk.get("fields")
                if isinstance(fields, dict):
                    for k, fv in fields.items():
                        if not isinstance(fv, list) or not fv:
                            continue
                        fid = fv[1] if len(fv) > 1 else None
                        fname = fv[0]
                        if k == "VARIABLE":
                            mark("v", fid, fname)
                            ids = ({fid} if isinstance(fid, str) and fid in self.var_map
                                   else self.var_name_ids.get(fname, set()))
                            if op in VAR_WRITE_OPS:
                                write_v.update(ids)
                            elif op == "data_showvariable":
                                show_v.update(ids)
                            elif op in ("data_hidevariable",):
                                pass
                            else:
                                # Includes data_variable and unknown extension
                                # blocks that use a VARIABLE field.
                                read_v.update(ids)
                        elif k == "LIST":
                            mark("l", fid, fname)
                            ids = ({fid} if isinstance(fid, str) and fid in self.list_map
                                   else self.list_name_ids.get(fname, set()))
                            if op in LIST_WRITE_OPS:
                                write_l.update(ids)
                            elif op == "data_showlist":
                                show_l.update(ids)
                            elif op in ("data_hidelist",):
                                pass
                            else:
                                # Includes list reporter blocks and unknown
                                # extension blocks that use a LIST field.
                                read_l.update(ids)
                        else:
                            mark_unknown_field(fid)
                    # "sensing_of" reads a variable by name, not by ID.
                    if op == "sensing_of":
                        prop = fields.get("PROPERTY")
                        if isinstance(prop, list) and prop and prop[0] is not None:
                            ids = self.var_name_ids.get(prop[0])
                            if ids:
                                used_v.update(ids)
                                read_v.update(ids)
                                sensed_v.update(ids)
                inputs = blk.get("inputs")
                if isinstance(inputs, dict):
                    for value in inputs.values():
                        scan_input(value)
                # A top-level variable/list reporter block is workspace display,
                # just like the primitive-array form used by most SB3 writers.
                if blk.get("topLevel") is True and op in ("data_variable", "data_listcontents"):
                    ids = set()
                    fv = (fields or {}).get("VARIABLE" if op == "data_variable" else "LIST")
                    if isinstance(fv, list) and fv:
                        fid = fv[1] if len(fv) > 1 else None
                        ids = ({fid} if isinstance(fid, str) and fid in
                               (self.var_map if op == "data_variable" else self.list_map)
                               else (self.var_name_ids if op == "data_variable"
                                     else self.list_name_ids).get(fv[0], set()))
                    (standalone_v if op == "data_variable" else standalone_l).update(ids)
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
            by_name = self.var_name_ids if op == "data_variable" else self.list_name_ids
            used = used_v if op == "data_variable" else used_l
            if isinstance(mid, str) and mid in table:
                ids = {mid}
                used.add(mid)
            elif pname is not None:
                ids = set(by_name.get(pname, set()))
                used.update(ids)
            else:
                ids = set()
            if mon.get("visible", True) is not False:
                (visible_v if op == "data_variable" else visible_l).update(ids)

        # Feature 1: a store that is not displayed (no visible monitor, no
        # show block, no standalone reporter) and has neither a writer nor a
        # reader is dead.  Hidden monitors alone do not keep a store alive.
        keep_v = used_v & (read_v | write_v | show_v | visible_v | standalone_v)
        keep_l = used_l & (read_l | write_l | show_l | visible_l | standalone_l)
        self._used_var_ids = keep_v
        self._used_list_ids = keep_l
        self._read_var_ids = read_v
        self._read_list_ids = read_l
        self._write_var_ids = write_v
        self._write_list_ids = write_l
        self._show_var_ids = show_v
        self._show_list_ids = show_l
        self._visible_var_ids = visible_v
        self._visible_list_ids = visible_l
        self._standalone_var_ids = standalone_v
        self._standalone_list_ids = standalone_l
        self._sensed_var_ids = sensed_v
        self._unknown_read_var_ids = unknown_read_v
        self._unknown_read_list_ids = unknown_read_l
        self._display_var_ids = visible_v | show_v | standalone_v
        self._display_list_ids = visible_l | show_l | standalone_l

    def _drop_obscured_shadows(self, targets) -> None:
        """Remove the unused shadow value under an input that a block covers.

        Scratch stores such an input as ``[3, block, shadow]``.  The ``shadow``
        value is serialized data for the editor's default slot, but the VM
        always uses the covering block, so it is dead weight.
        """
        st = self.stats
        for tgt in targets:
            if not isinstance(tgt, dict):
                continue
            blocks = tgt.get("blocks")
            if not isinstance(blocks, dict):
                continue
            for blk in blocks.values():
                if not isinstance(blk, dict):
                    continue
                inputs = blk.get("inputs")
                if not isinstance(inputs, dict):
                    continue
                for key, value in list(inputs.items()):
                    if (not isinstance(value, list) or len(value) < 3
                            or value[0] != 3):
                        continue
                    covered = value[1]
                    if isinstance(covered, str):
                        if covered not in blocks:
                            continue
                    elif isinstance(covered, list):
                        if not covered or not isinstance(covered[0], int):
                            continue
                    else:
                        continue
                    inputs[key] = [2, covered]
                    st["obscured_shadows_removed"] += 1

    def _remove_unreachable(self, project: dict) -> None:
        """Delete blocks that no script/definition can reach.

        Roots are hats, standalone workspace reporters, and unknown extension
        top-level blocks.  Custom-block definitions are roots only when a
        reachable ``procedures_call`` names them.  Broadcast receivers are
        roots only when a reachable sender uses the same message.
        """
        targets = project.get("targets")
        if not isinstance(targets, list):
            return
        st = self.stats
        blocks_by_ti = []
        for tgt in targets:
            blocks = tgt.get("blocks") if isinstance(tgt, dict) else None
            if not isinstance(blocks, dict):
                blocks = {}
            blocks_by_ti.append(blocks)

        defs_by_code: dict = {}
        receivers = []
        for ti, blocks in enumerate(blocks_by_ti):
            for bid, blk in blocks.items():
                if not isinstance(blk, dict):
                    continue
                op = blk.get("opcode")
                if op == "procedures_definition":
                    cb = (blk.get("inputs") or {}).get("custom_block")
                    pid = cb[1] if isinstance(cb, list) and len(cb) > 1 else None
                    proto = blocks.get(pid) if isinstance(pid, str) else None
                    mut = (proto or {}).get("mutation") or {}
                    code = mut.get("proccode")
                    if isinstance(code, str):
                        defs_by_code.setdefault((ti, code), []).append(bid)
                elif op == "event_whenbroadcastreceived":
                    fv = (blk.get("fields") or {}).get("BROADCAST_OPTION")
                    if isinstance(fv, list) and fv:
                        bid_id = fv[1] if len(fv) > 1 else None
                        receivers.append((ti, bid, bid_id if isinstance(bid_id, str) else None,
                                          fv[0] if isinstance(fv[0], str) else None))

        def is_top_root(op: str) -> bool:
            if not isinstance(op, str):
                return True
            if op == "event_whenbroadcastreceived":
                return False
            if op in ("procedures_definition", "procedures_prototype"):
                return False
            if op == "control_start_as_clone" or op.startswith("event_when"):
                return True
            if op in DATA_REPORTER_OPS:
                return True
            if op.startswith("data_"):
                return False
            if op.startswith(("motion_", "looks_", "sound_", "pen_")):
                return False
            if op.startswith("control_"):
                return False
            if op in SENSING_STACK_OPS:
                return False
            if op.startswith("sensing_"):
                # sensing_of and the reporter blocks are workspace values.
                return True
            if op.startswith("operator_") or op.startswith("argument_reporter"):
                return True
            if op in LOOSE_STACK_OPS:
                return False
            # Unknown extension block: keep it rather than risk deleting a hat.
            return True

        reachable = [set() for _ in targets]
        q: deque = deque()
        sent_ids: set = set()
        sent_names: set = set()

        def enqueue(ti: int, bid) -> None:
            if (isinstance(bid, str) and 0 <= ti < len(blocks_by_ti)
                    and bid in blocks_by_ti[ti] and bid not in reachable[ti]):
                q.append((ti, bid))

        # Initial roots.
        for ti, blocks in enumerate(blocks_by_ti):
            for bid, blk in blocks.items():
                if isinstance(blk, list):
                    # Standalone primitive reporter arrays are workspace data.
                    enqueue(ti, bid)
                elif isinstance(blk, dict) and blk.get("topLevel") is True:
                    if is_top_root(blk.get("opcode")):
                        enqueue(ti, bid)

        def add_broadcast_value(value, ti: int, seen: set | None = None) -> None:
            if seen is None:
                seen = set()
            if isinstance(value, list):
                if value and value[0] == 11:
                    if len(value) > 1 and isinstance(value[1], str):
                        sent_names.add(value[1])
                    if len(value) > 2 and isinstance(value[2], str):
                        sent_ids.add(value[2])
                    return
                for item in value[1:]:
                    add_broadcast_value(item, ti, seen)
            elif isinstance(value, dict):
                if "opcode" in value or "inputs" in value or "fields" in value:
                    fv = (value.get("fields") or {}).get("BROADCAST_OPTION")
                    if isinstance(fv, list) and fv:
                        if isinstance(fv[0], str):
                            sent_names.add(fv[0])
                        if len(fv) > 1 and isinstance(fv[1], str):
                            sent_ids.add(fv[1])
                    inputs = value.get("inputs")
                    if isinstance(inputs, dict):
                        for item in inputs.values():
                            add_broadcast_value(item, ti, seen)
                else:
                    # A raw inputs/fields mapping.
                    for item in value.values():
                        add_broadcast_value(item, ti, seen)
            elif isinstance(value, str):
                if value in seen:
                    return
                seen.add(value)
                blk = blocks_by_ti[ti].get(value)
                if isinstance(blk, dict):
                    add_broadcast_value(blk, ti, seen)

        def process_queue() -> None:
            while q:
                ti, bid = q.popleft()
                if bid in reachable[ti]:
                    continue
                blk = blocks_by_ti[ti].get(bid)
                if blk is None:
                    continue
                reachable[ti].add(bid)
                if isinstance(blk, list) or not isinstance(blk, dict):
                    continue
                op = blk.get("opcode")
                inputs = blk.get("inputs")
                if isinstance(inputs, dict):
                    for value in inputs.values():
                        if not isinstance(value, list):
                            continue
                        for item in value[1:]:
                            if isinstance(item, str):
                                enqueue(ti, item)
                nxt = blk.get("next")
                if isinstance(nxt, str):
                    enqueue(ti, nxt)
                if op == "procedures_definition":
                    cb = (blk.get("inputs") or {}).get("custom_block")
                    if isinstance(cb, list) and len(cb) > 1:
                        enqueue(ti, cb[1])
                elif op == "procedures_call":
                    code = ((blk.get("mutation") or {}).get("proccode"))
                    if isinstance(code, str):
                        for hat in defs_by_code.get((ti, code), []):
                            enqueue(ti, hat)
                if op in ("event_broadcast", "event_broadcastandwait"):
                    add_broadcast_value(blk.get("inputs"), ti)
                    add_broadcast_value(blk.get("fields"), ti)

        process_queue()
        while True:
            activated = False
            for ti, bid, bid_id, name in receivers:
                if bid in reachable[ti]:
                    continue
                if ((bid_id is not None and bid_id in sent_ids)
                        or (name is not None and name in sent_names)):
                    enqueue(ti, bid)
                    activated = True
            if not activated:
                break
            process_queue()

        # Prune blocks/comments and message definitions.
        for ti, tgt in enumerate(targets):
            if not isinstance(tgt, dict):
                continue
            blocks = blocks_by_ti[ti]
            kept = {bid: blk for bid, blk in blocks.items() if bid in reachable[ti]}
            st["unreachable_blocks_removed"] += len(blocks) - len(kept)
            st["procs_removed"] += sum(
                1 for bid, blk in blocks.items()
                if bid not in kept and isinstance(blk, dict)
                and blk.get("opcode") == "procedures_definition")
            for blk in kept.values():
                if not isinstance(blk, dict):
                    continue
                nxt = blk.get("next")
                if isinstance(nxt, str) and nxt not in kept:
                    blk["next"] = None
                par = blk.get("parent")
                if isinstance(par, str) and par not in kept:
                    blk["parent"] = None
            tgt["blocks"] = kept
            comments = tgt.get("comments")
            if isinstance(comments, dict):
                out = {}
                for cid, c in comments.items():
                    if not isinstance(c, dict):
                        continue
                    anchor = c.get("blockId")
                    # A comment with no block anchor is a free workspace note;
                    # it is not part of any script and is kept as user data.
                    if anchor is None or not isinstance(anchor, str):
                        out[cid] = c
                    elif anchor in kept:
                        out[cid] = c
                st["unreachable_comments_removed"] += len(comments) - len(out)
                tgt["comments"] = out

        # Broadcast definitions that no remaining block sends or receives.
        used_bc_ids: set = set(sent_ids)
        used_bc_names: set = set(sent_names)
        for ti, blocks in enumerate(blocks_by_ti):
            for bid, blk in blocks.items():
                if bid not in reachable[ti]:
                    continue
                if not isinstance(blk, dict):
                    continue
                fv = (blk.get("fields") or {}).get("BROADCAST_OPTION")
                if isinstance(fv, list) and fv:
                    if isinstance(fv[0], str):
                        used_bc_names.add(fv[0])
                    if len(fv) > 1 and isinstance(fv[1], str):
                        used_bc_ids.add(fv[1])
                # Also catch message menus embedded in inputs.
                add_broadcast_value(blk.get("inputs"), ti)
        # The helper above intentionally writes sent_*; capture its result too.
        used_bc_ids |= sent_ids
        used_bc_names |= sent_names
        for tgt in targets:
            if not isinstance(tgt, dict):
                continue
            bc = tgt.get("broadcasts")
            if not isinstance(bc, dict):
                continue
            out = {}
            for bid, ent in bc.items():
                name = ent[0] if isinstance(ent, list) and ent else ent
                if ((isinstance(bid, str) and bid in used_bc_ids)
                        or (isinstance(name, str) and name in used_bc_names)):
                    out[bid] = ent
            st["broadcasts_removed"] += len(bc) - len(out)
            tgt["broadcasts"] = out

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

    def _clear_initial_values(self, targets) -> None:
        """Blank saved initial values that are provably overwritten first.

        The analysis is deliberately conservative: every top-level script and
        every custom-block body is treated as an independent entry point.  A
        store is blanked only if every script that touches it performs a pure
        initialization (``set`` without reading the old value, or
        ``delete all of list``) before its first read.
        """
        st = self.stats
        scripts = []
        for tgt in targets:
            if not isinstance(tgt, dict):
                continue
            blocks = tgt.get("blocks")
            if not isinstance(blocks, dict):
                continue
            for bid, blk in blocks.items():
                if not isinstance(blk, dict) or blk.get("topLevel") is not True:
                    continue
                if blk.get("opcode") == "procedures_definition":
                    nxt = blk.get("next")
                    if isinstance(nxt, str) and nxt in blocks:
                        scripts.append((blocks, nxt))
                else:
                    scripts.append((blocks, bid))

        def field_matches(fv, kind: str, sid: str, sname) -> bool:
            if not isinstance(fv, list) or not fv:
                return False
            fid = fv[1] if len(fv) > 1 else None
            table = self.var_map if kind == "v" else self.list_map
            if isinstance(fid, str) and fid == sid:
                return True
            if ((not isinstance(fid, str)) or fid not in table):
                return fv[0] == sname
            return False

        def primitive_matches(p, kind: str, sid: str, sname) -> bool:
            if not isinstance(p, list) or not p:
                return False
            if kind == "v" and p[0] != 12:
                return False
            if kind == "l" and p[0] != 13:
                return False
            pid = p[2] if len(p) > 2 else None
            table = self.var_map if kind == "v" else self.list_map
            if isinstance(pid, str) and pid == sid:
                return True
            if ((not isinstance(pid, str)) or pid not in table):
                return len(p) > 1 and p[1] == sname
            return False

        def reporter_reads(blocks, blk, kind, sid, sname, seen) -> bool:
            if not isinstance(blk, dict):
                return False
            op = blk.get("opcode")
            fields = blk.get("fields") or {}
            if kind == "v":
                fv = fields.get("VARIABLE")
                if isinstance(fv, list) and field_matches(fv, "v", sid, sname):
                    if op != "data_setvariableto":
                        return True
                    # A set used as an expression is not a normal reporter, but
                    # treating its value as a read is the safe direction.
                    return True
                if op == "sensing_of":
                    prop = fields.get("PROPERTY")
                    if isinstance(prop, list) and prop and prop[0] == sname:
                        return True
            else:
                fv = fields.get("LIST")
                if isinstance(fv, list) and field_matches(fv, "l", sid, sname):
                    return True
            inputs = blk.get("inputs")
            if isinstance(inputs, dict):
                for key, value in inputs.items():
                    if key in ("SUBSTACK", "SUBSTACK2"):
                        continue
                    if expr_reads(blocks, value, kind, sid, sname, seen):
                        return True
            return False

        def expr_reads(blocks, value, kind, sid, sname, seen) -> bool:
            if not isinstance(value, list):
                return False
            if value and isinstance(value[0], int) and value[0] in (12, 13):
                return primitive_matches(value, kind, sid, sname)
            for item in value:
                if isinstance(item, list):
                    if expr_reads(blocks, item, kind, sid, sname, seen):
                        return True
                elif isinstance(item, str) and item in blocks:
                    if item in seen:
                        continue
                    seen.add(item)
                    if reporter_reads(blocks, blocks[item], kind, sid, sname, seen):
                        return True
            return False

        def block_access(blocks, blk, kind, sid, sname):
            """Return (reads, writes, pure_initialization)."""
            if not isinstance(blk, dict):
                return False, False, False
            op = blk.get("opcode")
            fields = blk.get("fields") or {}
            inputs = blk.get("inputs") or {}
            input_reads = False
            for key, value in inputs.items():
                if key in ("SUBSTACK", "SUBSTACK2"):
                    continue
                if expr_reads(blocks, value, kind, sid, sname, set()):
                    input_reads = True
                    break
            reads = input_reads
            writes = False
            pure = False
            fv = fields.get("VARIABLE" if kind == "v" else "LIST")
            matches = field_matches(fv, kind, sid, sname)
            if kind == "v":
                if matches:
                    if op == "data_setvariableto":
                        writes = True
                        # Reading the same variable in VALUE means the old value
                        # is used, so this is not an initialization.
                        pure = not input_reads
                    elif op == "data_changevariableby":
                        reads = True
                        writes = True
                    elif op == "control_for_each":
                        writes = True
                    elif op == "data_variable":
                        reads = True
                    elif op in ("data_showvariable", "data_hidevariable"):
                        pass
                    else:
                        # Unknown extension block using a VARIABLE field.
                        reads = True
                if op == "sensing_of":
                    prop = fields.get("PROPERTY")
                    if isinstance(prop, list) and prop and prop[0] == sname:
                        reads = True
            else:
                if matches:
                    if op == "data_deletealloflist":
                        writes = True
                        pure = True
                    elif op in LIST_WRITE_OPS:
                        writes = True
                    elif op in LIST_READ_OPS:
                        reads = True
                    elif op in ("data_showlist", "data_hidelist"):
                        pass
                    else:
                        reads = True
            return reads, writes, pure

        def successors(blocks, blk):
            out = []
            nxt = blk.get("next")
            if isinstance(nxt, str) and nxt in blocks:
                out.append(nxt)
            inputs = blk.get("inputs") or {}
            for key in ("SUBSTACK", "SUBSTACK2"):
                value = inputs.get(key)
                if isinstance(value, list):
                    for item in value[1:]:
                        if isinstance(item, str) and item in blocks:
                            out.append(item)
            return out

        def analyze_script(blocks, start, kind, sid, sname):
            touched = False
            has_init = False
            work = [(start, False)]
            seen = set()
            while work:
                bid, initialized = work.pop()
                if (bid, initialized) in seen:
                    continue
                seen.add((bid, initialized))
                blk = blocks.get(bid)
                if not isinstance(blk, dict):
                    continue
                reads, writes, pure = block_access(blocks, blk, kind, sid, sname)
                if reads or writes:
                    touched = True
                if reads and not initialized:
                    return touched, False, has_init
                if writes:
                    if pure:
                        initialized = True
                        has_init = True
                for nxt in successors(blocks, blk):
                    work.append((nxt, initialized))
            return touched, True, has_init

        def eligible(kind, sid) -> bool:
            used = self._used_var_ids if kind == "v" else self._used_list_ids
            if sid not in used:
                return False
            if kind == "v":
                if sid in self.var_cloud_ids:
                    return False
                if sid in self._display_var_ids:
                    return False
                if sid in self._unknown_read_var_ids:
                    return False
            else:
                if sid in self._display_list_ids:
                    return False
                if sid in self._unknown_read_list_ids:
                    return False
            return True

        def can_clear(kind, sid, sname) -> bool:
            touched_any = False
            initialized_any = False
            for blocks, start in scripts:
                touched, safe, has_init = analyze_script(
                    blocks, start, kind, sid, sname)
                if not touched:
                    continue
                touched_any = True
                if not safe:
                    return False
                initialized_any = initialized_any or has_init
            return touched_any and initialized_any

        for tgt in targets:
            if not isinstance(tgt, dict):
                continue
            variables = tgt.get("variables")
            if isinstance(variables, dict):
                for vid, ent in variables.items():
                    if not isinstance(ent, list) or len(ent) < 2:
                        continue
                    if not eligible("v", vid):
                        continue
                    if ent[1] == "":
                        continue
                    name = ent[0] if ent else self.var_orig_name.get(vid)
                    if can_clear("v", vid, name):
                        ent[1] = ""
                        st["vars_initialized"] += 1
            lists = tgt.get("lists")
            if isinstance(lists, dict):
                for lid, ent in lists.items():
                    if not isinstance(ent, list) or len(ent) < 2:
                        continue
                    if not eligible("l", lid):
                        continue
                    if ent[1] == []:
                        continue
                    name = ent[0] if ent else self.list_orig_name.get(lid)
                    if can_clear("l", lid, name):
                        ent[1] = []
                        st["lists_initialized"] += 1

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
        if isinstance(blocks, dict) and blocks and o.extract_duplicates:
            self._extract_duplicates(blocks)
        if isinstance(blocks, dict) and blocks and o.near_duplicates:
            self._extract_near_duplicates(blocks)
        if isinstance(blocks, dict) and blocks:
            self._normalize_parent_markers(blocks)
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

        # Extraction can remove duplicate blocks; drop comments that were
        # anchored to those blocks instead of leaving dangling references.
        final_blocks = tgt.get("blocks")
        comments = tgt.get("comments")
        if isinstance(final_blocks, dict) and isinstance(comments, dict):
            out = {}
            for cid, c in comments.items():
                if not isinstance(c, dict):
                    continue
                anchor = c.get("blockId")
                if anchor is None or not isinstance(anchor, str):
                    out[cid] = c
                elif anchor in final_blocks:
                    out[cid] = c
            tgt["comments"] = out

    # ------------------------------------------------------------------
    @staticmethod
    def _is_hat_opcode(op) -> bool:
        if not isinstance(op, str):
            return False
        return (op == "control_start_as_clone"
                or op == "procedures_definition"
                or op.startswith("event_when"))

    def _chain_ids(self, blocks, start, limit):
        out = []
        seen = set()
        cur = start
        while (isinstance(cur, str) and cur in blocks and cur not in seen
               and len(out) < limit):
            blk = blocks.get(cur)
            if not isinstance(blk, dict):
                break
            out.append(cur)
            seen.add(cur)
            cur = blk.get("next")
        return out

    def _collect_subgraph(self, blocks, start, follow_next=True):
        out = set()
        stack = [(start, follow_next)]
        while stack:
            bid, follow = stack.pop()
            if not isinstance(bid, str) or bid in out or bid not in blocks:
                continue
            out.add(bid)
            blk = blocks.get(bid)
            if not isinstance(blk, dict):
                continue
            inputs = blk.get("inputs")
            if isinstance(inputs, dict):
                for value in inputs.values():
                    if not isinstance(value, list):
                        continue
                    for item in value[1:]:
                        if isinstance(item, str) and item in blocks:
                            stack.append((item, True))
            if follow:
                nxt = blk.get("next")
                if isinstance(nxt, str):
                    stack.append((nxt, True))
        return out

    def _simplify_project(self, project: dict) -> None:
        """Run the cheap structural passes before duplicate extraction."""
        targets = project.get("targets") or []
        o = self.options
        if o.simplify_if_else:
            for tgt in targets:
                blocks = tgt.get("blocks") if isinstance(tgt, dict) else None
                if isinstance(blocks, dict) and blocks:
                    self._simplify_if_else(blocks)
        if o.remove_noops:
            # Definitions first: removing their calls can empty a broadcast
            # receiver, which the message pass then recognizes as a no-op.
            for tgt in targets:
                blocks = tgt.get("blocks") if isinstance(tgt, dict) else None
                if isinstance(blocks, dict) and blocks:
                    self._remove_noop_procedures(blocks)
            self._remove_noop_broadcasts(project)
        if o.inline_single_call:
            for tgt in targets:
                blocks = tgt.get("blocks") if isinstance(tgt, dict) else None
                if isinstance(blocks, dict) and blocks:
                    self._inline_single_call_procs(blocks)
        if o.propagate_constants:
            self._propagate_constants(targets, project.get("monitors"))
        if o.fold_constants:
            for tgt in targets:
                blocks = tgt.get("blocks") if isinstance(tgt, dict) else None
                if isinstance(blocks, dict) and blocks:
                    self._fold_numeric(blocks)
        if o.loop_duplicates:
            for tgt in targets:
                blocks = tgt.get("blocks") if isinstance(tgt, dict) else None
                if isinstance(blocks, dict) and blocks:
                    self._loopize_consecutive(blocks)

    def _simplify_if_else(self, blocks: dict) -> None:
        """Use ``if`` when an ``if/else`` has no else branch."""
        st = self.stats
        for blk in blocks.values():
            if not isinstance(blk, dict) or blk.get("opcode") != "control_if_else":
                continue
            inputs = blk.get("inputs")
            if not isinstance(inputs, dict):
                continue
            branch = inputs.get("SUBSTACK2")
            empty = branch is None
            if isinstance(branch, list):
                if len(branch) < 2 or branch[1] is None:
                    empty = True
                elif isinstance(branch[1], str) and branch[1] not in blocks:
                    empty = True
            if not empty:
                continue
            inputs.pop("SUBSTACK2", None)
            blk["opcode"] = "control_if"
            st["ifelse_converted"] += 1

    # ------------------------------------------------------------------
    def _chain_is_noop(self, blocks: dict, first) -> bool:
        """True when a stack body is empty or only ``stop this script``."""
        if not isinstance(first, str) or first not in blocks:
            return True
        ids = self._chain_ids(blocks, first, 100000)
        if not ids:
            return True
        for bid in ids:
            blk = blocks.get(bid)
            if not isinstance(blk, dict) or blk.get("opcode") != "control_stop":
                return False
            fv = (blk.get("fields") or {}).get("STOP_OPTION")
            if not (isinstance(fv, list) and fv and fv[0] == "this script"):
                return False
        return True

    def _splice_out(self, blocks: dict, bid) -> bool:
        """Remove a stack block and reconnect its predecessor and successor."""
        blk = blocks.get(bid)
        if not isinstance(blk, dict):
            return False
        nxt = blk.get("next")
        nxt = nxt if isinstance(nxt, str) and nxt in blocks else None
        parent_id = blk.get("parent")
        parent = blocks.get(parent_id) if isinstance(parent_id, str) else None
        linked = False
        if isinstance(parent, dict):
            if parent.get("next") == bid:
                parent["next"] = nxt
                linked = True
            inputs = parent.get("inputs")
            if isinstance(inputs, dict):
                for value in inputs.values():
                    if isinstance(value, list) and len(value) > 1 and value[1] == bid:
                        value[1] = nxt
                        linked = True
            if not linked:
                parent_id = None
        if not linked:
            # A loose/top-level stack: promote the continuation in place.
            if nxt is not None:
                nb = blocks.get(nxt)
                if isinstance(nb, dict):
                    nb["parent"] = None
                    nb["topLevel"] = True
                    if "x" in blk:
                        nb["x"] = blk["x"]
                    if "y" in blk:
                        nb["y"] = blk["y"]
        else:
            if nxt is not None:
                nb = blocks.get(nxt)
                if isinstance(nb, dict):
                    nb["parent"] = parent_id
        for x in self._collect_subgraph(blocks, bid, False):
            blocks.pop(x, None)
        return True

    def _remove_noop_procedures(self, blocks: dict) -> None:
        """Drop definitions that do nothing, together with their calls."""
        st = self.stats
        for _ in range(200):
            protos = {bid: b for bid, b in blocks.items()
                      if isinstance(b, dict)
                      and b.get("opcode") == "procedures_prototype"}
            defs = []
            calls = {}
            for bid, b in blocks.items():
                if not isinstance(b, dict):
                    continue
                op = b.get("opcode")
                if op == "procedures_call":
                    code = (b.get("mutation") or {}).get("proccode")
                    calls.setdefault(code, []).append(bid)
            code_count = {}
            for bid, b in blocks.items():
                if not isinstance(b, dict) or b.get("opcode") != "procedures_definition":
                    continue
                cb = (b.get("inputs") or {}).get("custom_block")
                pid = cb[1] if isinstance(cb, list) and len(cb) > 1 else None
                proto = blocks.get(pid) if isinstance(pid, str) else None
                mut = (proto or {}).get("mutation") or {}
                code = mut.get("proccode")
                if not isinstance(code, str):
                    continue
                code_count[code] = code_count.get(code, 0) + 1
                defs.append((bid, pid, code))
            targets = []
            for hat, pid, code in defs:
                if code_count.get(code, 0) != 1:
                    # Ambiguous proccode: a call cannot be bound reliably.
                    continue
                body = blocks[hat].get("next")
                if self._chain_is_noop(blocks, body):
                    targets.append((hat, pid, code, body))
            if not targets:
                break
            for hat, pid, code, body in targets:
                for cid in list(calls.get(code, [])):
                    if cid in blocks and self._splice_out(blocks, cid):
                        st["noop_calls_removed"] += 1
                if isinstance(body, str) and body in blocks:
                    for x in self._collect_subgraph(blocks, body, True):
                        blocks.pop(x, None)
                blocks.pop(hat, None)
                if isinstance(pid, str):
                    blocks.pop(pid, None)
                st["noop_procs_removed"] += 1

    def _remove_noop_broadcasts(self, project: dict) -> None:
        """Drop empty broadcast receivers and sends that can never run code."""
        st = self.stats
        targets = project.get("targets") or []

        defs = {}
        for tgt in targets:
            if not isinstance(tgt, dict):
                continue
            for bid, ent in (tgt.get("broadcasts") or {}).items():
                name = ent[0] if isinstance(ent, list) and ent else ent
                defs[bid] = name

        def message_key(name, mid):
            if isinstance(mid, str) and mid in defs:
                return mid
            return name

        effective = set()
        noop_receivers = []
        for tgt in targets:
            if not isinstance(tgt, dict):
                continue
            blocks = tgt.get("blocks")
            if not isinstance(blocks, dict):
                continue
            for bid, blk in blocks.items():
                if not isinstance(blk, dict) \
                        or blk.get("opcode") != "event_whenbroadcastreceived":
                    continue
                fv = (blk.get("fields") or {}).get("BROADCAST_OPTION")
                if not isinstance(fv, list) or not fv:
                    continue
                name = fv[0] if isinstance(fv[0], str) else None
                mid = fv[1] if len(fv) > 1 and isinstance(fv[1], str) else None
                if self._chain_is_noop(blocks, blk.get("next")):
                    noop_receivers.append((blocks, bid))
                else:
                    effective.add(message_key(name, mid))

        for blocks, hat_id in noop_receivers:
            for x in self._collect_subgraph(blocks, hat_id, True):
                blocks.pop(x, None)
            st["noop_receivers_removed"] += 1

        sends = []
        for tgt in targets:
            if not isinstance(tgt, dict):
                continue
            blocks = tgt.get("blocks")
            if not isinstance(blocks, dict):
                continue
            for bid, blk in blocks.items():
                if not isinstance(blk, dict) \
                        or blk.get("opcode") not in ("event_broadcast",
                                                     "event_broadcastandwait"):
                    continue
                name = mid = None
                inp = (blk.get("inputs") or {}).get("BROADCAST_INPUT")
                if isinstance(inp, list) and len(inp) > 1 and isinstance(inp[1], list):
                    arr = inp[1]
                    if len(arr) > 1 and isinstance(arr[1], str):
                        name = arr[1]
                    if len(arr) > 2 and isinstance(arr[2], str):
                        mid = arr[2]
                if message_key(name, mid) not in effective:
                    sends.append((blocks, bid))
        for blocks, bid in sends:
            if self._splice_out(blocks, bid):
                st["noop_broadcasts_removed"] += 1

        # Recompute which message definitions are still referenced.
        used = set()
        for tgt in targets:
            if not isinstance(tgt, dict):
                continue
            for blk in (tgt.get("blocks") or {}).values():
                if not isinstance(blk, dict):
                    continue
                fv = (blk.get("fields") or {}).get("BROADCAST_OPTION")
                if isinstance(fv, list) and fv:
                    if isinstance(fv[0], str):
                        used.add(fv[0])
                    if len(fv) > 1 and isinstance(fv[1], str):
                        used.add(fv[1])
                if blk.get("opcode") in ("event_broadcast",
                                         "event_broadcastandwait"):
                    inp = (blk.get("inputs") or {}).get("BROADCAST_INPUT")
                    if isinstance(inp, list) and len(inp) > 1 \
                            and isinstance(inp[1], list):
                        arr = inp[1]
                        if len(arr) > 1 and isinstance(arr[1], str):
                            used.add(arr[1])
                        if len(arr) > 2 and isinstance(arr[2], str):
                            used.add(arr[2])
        for tgt in targets:
            if not isinstance(tgt, dict):
                continue
            bc = tgt.get("broadcasts")
            if not isinstance(bc, dict):
                continue
            out = {}
            for bid, ent in bc.items():
                name = ent[0] if isinstance(ent, list) and ent else ent
                if bid in used or (isinstance(name, str) and name in used):
                    out[bid] = ent
            removed = len(bc) - len(out)
            if removed:
                st["noop_messages_removed"] += removed
                tgt["broadcasts"] = out

    def _contains_this_script_stop(self, blocks: dict, start) -> bool:
        if not isinstance(start, str) or start not in blocks:
            return False
        for bid in self._collect_subgraph(blocks, start, True):
            blk = blocks.get(bid)
            if not isinstance(blk, dict) or blk.get("opcode") != "control_stop":
                continue
            fv = (blk.get("fields") or {}).get("STOP_OPTION")
            if isinstance(fv, list) and fv and fv[0] == "this script":
                return True
        return False

    def _enclosing_definition_is_warp(self, blocks: dict, block_id) -> bool:
        seen = set()
        cur = blocks.get(block_id) if isinstance(block_id, str) else None
        while isinstance(cur, dict):
            parent = cur.get("parent")
            if not isinstance(parent, str) or parent in seen or parent not in blocks:
                return False
            seen.add(parent)
            blk = blocks.get(parent)
            if not isinstance(blk, dict):
                return False
            if blk.get("opcode") == "procedures_definition":
                cb = (blk.get("inputs") or {}).get("custom_block")
                pid = cb[1] if isinstance(cb, list) and len(cb) > 1 else None
                proto = blocks.get(pid) if isinstance(pid, str) else None
                mut = (proto or {}).get("mutation") or {}
                return str(mut.get("warp")) == "true"
            cur = blk
        return False

    def _inline_single_call_procs(self, blocks: dict) -> None:
        """Move a non-warp definition used exactly once to its call site."""
        st = self.stats
        while True:
            protos = {bid: b for bid, b in blocks.items()
                      if isinstance(b, dict)
                      and b.get("opcode") == "procedures_prototype"}
            defs = []
            calls = {}
            for bid, b in blocks.items():
                if not isinstance(b, dict):
                    continue
                if b.get("opcode") == "procedures_call":
                    code = (b.get("mutation") or {}).get("proccode")
                    calls.setdefault(code, []).append(bid)
                elif b.get("opcode") == "procedures_definition":
                    cb = (b.get("inputs") or {}).get("custom_block")
                    pid = cb[1] if isinstance(cb, list) and len(cb) > 1 else None
                    proto = blocks.get(pid) if isinstance(pid, str) else None
                    mut = (proto or {}).get("mutation") or {}
                    defs.append((bid, pid, mut.get("proccode"), mut))
            code_count = {}
            for _hat, _pid, code, _mut in defs:
                if isinstance(code, str):
                    code_count[code] = code_count.get(code, 0) + 1

            done = False
            for hat, pid, code, mut in defs:
                if not isinstance(code, str) or code_count.get(code, 0) != 1:
                    continue
                if str(mut.get("warp")) == "true":
                    continue
                try:
                    arg_ids = json.loads(mut.get("argumentids") or "[]")
                except (TypeError, ValueError):
                    arg_ids = []
                if arg_ids:
                    continue
                ids = calls.get(code, [])
                if len(ids) != 1:
                    continue
                body = blocks[hat].get("next")
                if not isinstance(body, str) or body not in blocks:
                    continue
                if self._contains_this_script_stop(blocks, body):
                    continue
                has_arg_reporter = False
                for x in self._collect_subgraph(blocks, body, True):
                    xb = blocks.get(x)
                    if isinstance(xb, dict) and str(xb.get("opcode", "")).startswith(
                            "argument_reporter"):
                        has_arg_reporter = True
                        break
                if has_arg_reporter:
                    continue
                call_id = ids[0]
                call = blocks.get(call_id)
                if not isinstance(call, dict):
                    continue
                parent_id = call.get("parent")
                if not isinstance(parent_id, str) or parent_id not in blocks:
                    continue
                if self._enclosing_definition_is_warp(blocks, parent_id):
                    continue
                parent = blocks[parent_id]
                replaced = False
                if parent.get("next") == call_id:
                    parent["next"] = body
                    replaced = True
                inputs = parent.get("inputs")
                if isinstance(inputs, dict):
                    for value in inputs.values():
                        if isinstance(value, list) and len(value) > 1 \
                                and value[1] == call_id:
                            value[1] = body
                            replaced = True
                if not replaced:
                    continue
                chain = self._chain_ids(blocks, body, 1000000)
                if not chain:
                    continue
                last = chain[-1]
                call_next = call.get("next")
                call_next = call_next if isinstance(call_next, str) else None
                blocks[body]["parent"] = parent_id
                blocks[last]["next"] = call_next
                if call_next is not None and call_next in blocks:
                    blocks[call_next]["parent"] = last
                for x in self._collect_subgraph(blocks, call_id, False):
                    blocks.pop(x, None)
                blocks.pop(hat, None)
                if isinstance(pid, str):
                    blocks.pop(pid, None)
                st["procs_inlined"] += 1
                done = True
                break
            if not done:
                break

    # ------------------------------------------------------------------
    def _literal_number(self, entry):
        """Read a numeric literal from an SB3 input entry, or None for a block."""
        if not isinstance(entry, list) or len(entry) < 2:
            return 0.0
        item = entry[1]
        if isinstance(item, list):
            if not item:
                return 0.0
            if len(item) >= 2 and item[0] in (4, 5, 6, 7, 8, 10):
                return js_to_number(item[1])
            return None
        if isinstance(item, str):
            return None
        if item is None:
            return 0.0
        return js_to_number(item)

    def _eval_foldable(self, blk: dict):
        """Evaluate an all-literal numeric reporter, or return None."""
        op = blk.get("opcode")
        inputs = blk.get("inputs") or {}
        if op in ("operator_add", "operator_subtract", "operator_multiply",
                  "operator_divide", "operator_mod"):
            # Ignore blocks that do not use the standard numeric inputs at
            # all (malformed or extension-made): missing recognised inputs
            # would otherwise look like "0 + 0" and delete real reporters.
            if "NUM1" not in inputs and "NUM2" not in inputs:
                return None
            left = self._literal_number(inputs.get("NUM1"))
            right = self._literal_number(inputs.get("NUM2"))
            if left is None or right is None:
                return None
            try:
                if op == "operator_add":
                    return left + right
                if op == "operator_subtract":
                    return left - right
                if op == "operator_multiply":
                    return left * right
                if op == "operator_divide":
                    return js_divide(left, right)
                return js_mod(left, right)
            except OverflowError:
                return float("inf")
        if op == "operator_round":
            if "NUM" not in inputs:
                return None
            value = self._literal_number(inputs.get("NUM"))
            return None if value is None else js_round(value)
        if op == "operator_mathop":
            if "NUM" not in inputs:
                return None
            value = self._literal_number(inputs.get("NUM"))
            if value is None:
                return None
            fv = (blk.get("fields") or {}).get("OPERATOR")
            name = fv[0] if isinstance(fv, list) and fv else None
            if name == "abs":
                return abs(value)
            if name == "floor":
                return js_floor(value)
            if name == "ceiling":
                return js_ceil(value)
            if name == "sqrt":
                try:
                    return math.sqrt(value)
                except ValueError:
                    return float("nan")
            # Transcendental functions are intentionally not folded: their
            # last-bit results can differ between JavaScript and Python.
            return None
        return None

    def _fold_numeric(self, blocks: dict) -> None:
        """Replace numeric-only reporter trees with their computed literal."""
        st = self.stats
        foldable = {"operator_add", "operator_subtract", "operator_multiply",
                    "operator_divide", "operator_mod", "operator_round",
                    "operator_mathop"}
        refs = {}
        for blk in blocks.values():
            if not isinstance(blk, dict):
                continue
            for value in (blk.get("inputs") or {}).values():
                if not isinstance(value, list):
                    continue
                for item in value[1:]:
                    if isinstance(item, str):
                        refs[item] = refs.get(item, 0) + 1
        for _ in range(100000):
            changed = False
            for pid, parent in list(blocks.items()):
                if not isinstance(parent, dict):
                    continue
                inputs = parent.get("inputs")
                if not isinstance(inputs, dict):
                    continue
                for key, entry in list(inputs.items()):
                    if (not isinstance(entry, list) or len(entry) < 2
                            or not isinstance(entry[1], str)
                            or key.startswith("SUBSTACK")):
                        continue
                    cid = entry[1]
                    child = blocks.get(cid)
                    if not isinstance(child, dict):
                        continue
                    if child.get("opcode") not in foldable:
                        continue
                    if child.get("topLevel") is True:
                        continue
                    if child.get("parent") not in (pid, None):
                        continue
                    if refs.get(cid, 0) != 1:
                        continue
                    value = self._eval_foldable(child)
                    if value is None or math.isnan(value):
                        continue
                    text = js_number_str(value)
                    if text is None or len(text) > 64:
                        continue
                    inputs[key] = [1, [4, text]]
                    for x in self._collect_subgraph(blocks, cid, False):
                        blocks.pop(x, None)
                        refs.pop(x, None)
                    st["const_values_folded"] += 1
                    changed = True
                    break
                if changed:
                    break
            if not changed:
                break

    # ------------------------------------------------------------------
    def _canonical_block(self, blocks: dict, bid, cache: dict,
                         include_next: bool = False, stack=frozenset()):
        key = (bid, include_next)
        if key in cache:
            return cache[key]
        if bid in stack:
            return ("cycle",)
        blk = blocks.get(bid)
        if isinstance(blk, list):
            value = ("prim", self._freeze(blk))
            cache[key] = value
            return value
        if not isinstance(blk, dict):
            return ("missing",)
        nstack = stack | {bid}
        fields = tuple(sorted((k, self._freeze(v))
                              for k, v in (blk.get("fields") or {}).items()))
        inputs = []
        for k, value in sorted((blk.get("inputs") or {}).items()):
            if not isinstance(value, list):
                inputs.append((k, ("value", self._freeze(value))))
                continue
            items = []
            for item in value:
                if isinstance(item, str) and item in blocks:
                    items.append(("ref", self._canonical_block(
                        blocks, item, cache, True, nstack)))
                elif isinstance(item, list):
                    items.append(("list", self._freeze(item)))
                else:
                    items.append(("value", item))
            inputs.append((k, tuple(items)))
        value = (blk.get("opcode"), fields, tuple(inputs),
                 self._freeze(blk.get("mutation") or {}),
                 bool(blk.get("shadow")))
        if include_next:
            nxt = blk.get("next")
            nval = (self._canonical_block(blocks, nxt, cache, True, nstack)
                    if isinstance(nxt, str) and nxt in blocks else None)
            value = value + (nval,)
        cache[key] = value
        return value

    @staticmethod
    def _freeze(value):
        if isinstance(value, dict):
            return tuple(sorted((str(k), Compressor._freeze(v))
                                for k, v in value.items()))
        if isinstance(value, list):
            return tuple(Compressor._freeze(v) for v in value)
        return value

    def _loopize_consecutive(self, blocks: dict) -> None:
        """Turn consecutive identical groups into a ``repeat`` block."""
        st = self.stats
        if not isinstance(blocks, dict) or len(blocks) < 3:
            return
        for _ in range(200):
            cache = {}
            next_targets = set()
            for blk in blocks.values():
                if isinstance(blk, dict) and isinstance(blk.get("next"), str):
                    next_targets.add(blk["next"])
            starts = [bid for bid in blocks
                      if bid not in next_targets and isinstance(blocks[bid], dict)]
            best = None
            for start in starts:
                if self._is_hat_opcode(blocks[start].get("opcode")):
                    chain = self._chain_ids(blocks, start, 100000)
                    if not chain:
                        continue
                    first_index = 1
                else:
                    chain = self._chain_ids(blocks, start, 100000)
                    first_index = 0
                    if blocks[start].get("topLevel") is True:
                        first_index = 1
                if len(chain) - first_index < 2:
                    continue
                keys = [self._canonical_block(blocks, bid, cache, False)
                        for bid in chain]
                limit = min(40, len(chain))
                for i in range(first_index, len(chain) - 1):
                    max_l = min(limit, (len(chain) - i) // 2)
                    for length in range(1, max_l + 1):
                        count = 1
                        while i + (count + 1) * length <= len(chain):
                            ok = True
                            for j in range(length):
                                if keys[i + count * length + j] != keys[i + j]:
                                    ok = False
                                    break
                            if not ok:
                                break
                            count += 1
                        if count < 2:
                            continue
                        removed = set()
                        for k in range(1, count):
                            for bid in chain[i + k * length:
                                            i + (k + 1) * length]:
                                removed |= self._collect_subgraph(blocks, bid, False)
                        removed -= set(chain[i:i + length])
                        saved = len(removed)
                        if saved < 2:
                            continue
                        score = (saved, length, count)
                        if best is None or score > best[0]:
                            best = (score, chain, i, length, count, removed)
            if best is None:
                return
            _score, chain, i, length, count, removed = best
            saved = _score[0]
            first = chain[i]
            last_first_unit = chain[i + length - 1]
            last = chain[i + length * count - 1]
            parent_id = blocks[first].get("parent")
            if not isinstance(parent_id, str) or parent_id not in blocks:
                return
            cont = blocks[last].get("next")
            cont = cont if isinstance(cont, str) and cont in blocks else None
            before = copy.deepcopy(blocks)
            rid = "L1"
            n = 1
            while rid in blocks:
                n += 1
                rid = f"L{n}"
            rep = {
                "opcode": "control_repeat",
                "next": cont,
                "parent": parent_id,
                "inputs": {
                    "TIMES": [1, [6, str(count)]],
                    "SUBSTACK": [2, first],
                },
                "fields": {},
                "shadow": False,
                "topLevel": False,
            }
            blocks[rid] = rep
            blocks[first]["parent"] = rid
            blocks[last_first_unit]["next"] = None
            parent = blocks[parent_id]
            if parent.get("next") == first:
                parent["next"] = rid
            else:
                for value in (parent.get("inputs") or {}).values():
                    if isinstance(value, list) and len(value) > 1 \
                            and value[1] == first:
                        value[1] = rid
            if cont is not None:
                blocks[cont]["parent"] = rid
            for bid in removed:
                blocks.pop(bid, None)
            old_size = len(json.dumps(before, ensure_ascii=False,
                                      separators=(",", ":")))
            new_size = len(json.dumps(blocks, ensure_ascii=False,
                                      separators=(",", ":")))
            if new_size >= old_size:
                blocks.clear()
                blocks.update(before)
                return
            st["loops_created"] += 1
            st["loop_blocks_saved"] += saved

    # ------------------------------------------------------------------
    @staticmethod
    def _value_literal(value):
        """Return ``(primitive_type, text)`` for a stored variable value."""
        if isinstance(value, bool):
            # Booleans are not representable as a Scratch variable literal.
            return None
        if isinstance(value, (int, float)):
            text = js_number_str(value)
            return None if text is None else (4, text)
        if isinstance(value, str):
            return (10, value)
        return None

    @staticmethod
    def _set_literal(blk: dict):
        """Read the literal written by ``set variable to``, or None."""
        entry = (blk.get("inputs") or {}).get("VALUE")
        if not isinstance(entry, list) or len(entry) < 2:
            return None
        item = entry[1]
        if not isinstance(item, list) or not item:
            return None
        kind = item[0]
        if kind in (4, 5, 6, 7, 8):
            text = item[1] if len(item) > 1 else "0"
            return (4, str(text))
        if kind == 10:
            text = item[1] if len(item) > 1 else ""
            return (10, str(text))
        return None

    def _propagate_constants(self, targets, monitors=None) -> None:
        """Replace reads of variables whose value can never change.

        Two cases are handled:

        * a variable that is never written: every read sees its saved value;
        * a variable whose every write stores the same literal: reads that
          follow such a write in the same script see that literal.  All writes
          store the same value, so once a script has written it the variable
          can never hold anything else again, which makes the dominance
          analysis monotone and safe even across loops.

        Displayed, sensed, cloud, monitored, and extension-touched stores are
        left alone, and a replacement is applied only when the serialized
        project actually shrinks.
        """
        st = self.stats
        store = {}
        for tgt in targets:
            if not isinstance(tgt, dict):
                continue
            variables = tgt.get("variables")
            if not isinstance(variables, dict):
                continue
            for vid, ent in variables.items():
                if isinstance(ent, list) and ent:
                    name = ent[0]
                    value = ent[1] if len(ent) > 1 else ""
                else:
                    name, value = str(ent), ""
                store[vid] = (tgt, name, value)
        if not store:
            return

        def jlen(value) -> int:
            return len(json.dumps(value, ensure_ascii=False,
                                  separators=(",", ":")))

        bad = set(self.var_cloud_ids)
        bad |= self._display_var_ids
        bad |= self._sensed_var_ids
        bad |= self._unknown_read_var_ids
        for mon in monitors or []:
            if not isinstance(mon, dict) or mon.get("opcode") != "data_variable":
                continue
            mid = mon.get("id")
            if isinstance(mid, str) and mid in store:
                bad.add(mid)
            pname = (mon.get("params") or {}).get("VARIABLE")
            if isinstance(pname, str):
                bad |= set(self.var_name_ids.get(pname, set()))

        def ref_vid(arr):
            if not isinstance(arr, list) or not arr or arr[0] != 12:
                return None
            pid = arr[2] if len(arr) > 2 else None
            if isinstance(pid, str) and pid in store:
                return pid
            name = arr[1] if len(arr) > 1 else None
            if isinstance(name, str):
                ids = self.var_name_ids.get(name)
                if ids and len(ids) == 1:
                    vid = next(iter(ids))
                    if vid in store:
                        return vid
            return None

        def block_vid(blk):
            fv = (blk.get("fields") or {}).get("VARIABLE")
            if not isinstance(fv, list) or not fv:
                return None
            fid = fv[1] if len(fv) > 1 else None
            if isinstance(fid, str) and fid in store:
                return fid
            name = fv[0]
            if isinstance(name, str):
                ids = self.var_name_ids.get(name)
                if ids and len(ids) == 1:
                    vid = next(iter(ids))
                    if vid in store:
                        return vid
            return None

        blocks_by_tgt = []
        for tgt in targets:
            blocks = tgt.get("blocks") if isinstance(tgt, dict) else None
            blocks_by_tgt.append(blocks if isinstance(blocks, dict) else {})

        # Find every write so a single unusual write disables the variable.
        writes = {}
        for blocks in blocks_by_tgt:
            for blk in blocks.values():
                if not isinstance(blk, dict):
                    continue
                fv = (blk.get("fields") or {}).get("VARIABLE")
                if not isinstance(fv, list) or not fv:
                    continue
                op = blk.get("opcode")
                fid = fv[1] if len(fv) > 1 else None
                if isinstance(fid, str) and fid in store:
                    ids = {fid}
                else:
                    ids = set(self.var_name_ids.get(fv[0], set())) & set(store)
                if not ids:
                    continue
                if op == "data_setvariableto":
                    pair = self._set_literal(blk)
                    if pair is None:
                        bad |= ids
                    else:
                        for vid in ids:
                            writes.setdefault(vid, []).append(pair)
                elif op in VAR_WRITE_OPS:
                    bad |= ids
                elif op in ("data_variable", "data_showvariable",
                            "data_hidevariable"):
                    pass
                else:
                    # Unknown extension block using a VARIABLE field: it may
                    # write, so leave the store alone.
                    bad |= ids

        always = {}
        dominated = {}
        for vid, (_tgt, _name, value) in store.items():
            if vid in bad:
                continue
            init = self._value_literal(value)
            ws = writes.get(vid)
            if ws is None:
                if init is not None:
                    always[vid] = init
                continue
            if not ws:
                continue
            first = ws[0]
            if any(w != first for w in ws):
                continue
            if init is not None and init == first:
                always[vid] = first
            else:
                # Reads before the first write still see the saved value, so
                # only script-order dominated reads may be replaced.
                dominated[vid] = first

        if not always and not dominated:
            return

        # Count references so a store can be dropped once all reads are gone.
        ref_count = {}

        def count_refs(node):
            if isinstance(node, list):
                if node and node[0] == 12:
                    vid = ref_vid(node)
                    if vid is not None:
                        ref_count[vid] = ref_count.get(vid, 0) + 1
                    return
                for item in node:
                    count_refs(item)
            elif isinstance(node, dict):
                for value in node.values():
                    count_refs(value)

        input_refs = {}
        for blocks in blocks_by_tgt:
            for bid, blk in blocks.items():
                if isinstance(blk, list):
                    count_refs(blk)
                    continue
                if not isinstance(blk, dict):
                    continue
                if blk.get("opcode") == "data_variable":
                    vid = block_vid(blk)
                    if vid is not None:
                        ref_count[vid] = ref_count.get(vid, 0) + 1
                count_refs(blk.get("inputs"))
                for entry in (blk.get("inputs") or {}).values():
                    if not isinstance(entry, list):
                        continue
                    for item in entry[1:]:
                        if isinstance(item, str) and item in blocks:
                            input_refs[item] = input_refs.get(item, 0) + 1

        edits = {}

        def record_prim(owner, key, entry, vid, pair):
            new_entry = [1, [pair[0], pair[1]]]
            edits.setdefault(vid, []).append({
                "inputs": owner,
                "key": key,
                "new": new_entry,
                "remove": None,
                "delta": jlen(new_entry) - jlen(entry),
            })

        def record_block(blocks, owner, key, entry, vid, bid, blk, pair):
            if input_refs.get(bid, 0) != 1 or blk.get("next") is not None:
                return
            new_entry = [1, [pair[0], pair[1]]]
            delta = (jlen(new_entry) - jlen(entry)
                     - (jlen(bid) + jlen(blk) + 2))
            edits.setdefault(vid, []).append({
                "inputs": owner,
                "key": key,
                "new": new_entry,
                "remove": bid,
                "blocks": blocks,
                "delta": delta,
            })

        for tgt, blocks in zip(targets, blocks_by_tgt):
            if not isinstance(tgt, dict) or not blocks:
                continue
            done = set()

            def scan_inputs(blk, known, owner_id):
                inputs = blk.get("inputs")
                if not isinstance(inputs, dict):
                    return
                for key, entry in list(inputs.items()):
                    if not isinstance(entry, list) or len(entry) < 2:
                        continue
                    if key.startswith("SUBSTACK"):
                        continue
                    child = entry[1]
                    if isinstance(child, list):
                        vid = ref_vid(child)
                        if vid is not None and vid in known:
                            record_prim(inputs, key, entry, vid, known[vid])
                    elif isinstance(child, str) and child in blocks:
                        cb = blocks.get(child)
                        if not isinstance(cb, dict) or child in done:
                            continue
                        if cb.get("opcode") == "data_variable":
                            vid = block_vid(cb)
                            if vid is not None and vid in known:
                                record_block(blocks, inputs, key, entry, vid,
                                             child, cb, known[vid])
                        else:
                            done.add(child)
                            scan_inputs(cb, known, child)

            def walk_chain(start, known):
                cur = start
                seen = set()
                while isinstance(cur, str) and cur in blocks \
                        and cur not in seen and cur not in done:
                    seen.add(cur)
                    blk = blocks.get(cur)
                    if not isinstance(blk, dict):
                        break
                    done.add(cur)
                    scan_inputs(blk, known, cur)
                    if blk.get("opcode") == "data_setvariableto":
                        vid = block_vid(blk)
                        if vid in dominated \
                                and self._set_literal(blk) == dominated[vid]:
                            known = dict(known)
                            known[vid] = dominated[vid]
                    for key, entry in (blk.get("inputs") or {}).items():
                        if not key.startswith("SUBSTACK"):
                            continue
                        if isinstance(entry, list) and len(entry) > 1 \
                                and isinstance(entry[1], str):
                            walk_chain(entry[1], dict(known))
                    cur = blk.get("next")

            for bid, blk in blocks.items():
                if not isinstance(blk, dict) or bid in done:
                    continue
                parent = blk.get("parent")
                if blk.get("topLevel") is True \
                        or not (isinstance(parent, str) and parent in blocks):
                    walk_chain(bid, dict(always))

        for vid in list(edits):
            items = edits[vid]
            pair = always.get(vid)
            total = sum(e["delta"] for e in items)
            drop_store = False
            variables = None
            if pair is not None and writes.get(vid) is None \
                    and ref_count.get(vid, 0) - len(items) == 0:
                tgt, _name, _value = store[vid]
                variables = tgt.get("variables")
                if isinstance(variables, dict) and vid in variables:
                    total -= jlen(vid) + jlen(variables[vid]) + 2
                    drop_store = True
            if total >= 0:
                continue
            for e in items:
                e["inputs"][e["key"]] = e["new"]
                if e["remove"] is not None:
                    e["blocks"].pop(e["remove"], None)
            st["const_vars_inlined"] += 1
            st["const_reads_inlined"] += len(items)
            if drop_store:
                del variables[vid]
                self._used_var_ids.discard(vid)
                self._read_var_ids.discard(vid)
                self._dropped_var_ids.add(vid)

    def _chain_argument_params(self, blocks, ids):
        """Return the definition arguments used by a chain, in order.

        The result is a list of ``(name, is_boolean)`` pairs, or ``None`` when
        the chain cannot be parameterised safely (a malformed reporter or one
        name used with two different argument types).  Only reporters nested
        inside the chain are considered; the chain continuation is not walked.
        """
        params = []
        kinds = {}

        def scan(bid, stack):
            if not isinstance(bid, str) or bid not in blocks or bid in stack:
                return True
            blk = blocks.get(bid)
            if not isinstance(blk, dict):
                return True
            op = blk.get("opcode")
            if op in ("argument_reporter_string_number",
                      "argument_reporter_boolean"):
                fv = (blk.get("fields") or {}).get("VALUE")
                name = fv[0] if isinstance(fv, list) and fv else None
                if not isinstance(name, str) or not name:
                    return False
                is_bool = op == "argument_reporter_boolean"
                if name in kinds:
                    if kinds[name] != is_bool:
                        return False
                else:
                    kinds[name] = is_bool
                    params.append((name, is_bool))
                return True
            inputs = blk.get("inputs")
            if isinstance(inputs, dict):
                # Sorted keys keep the generated parameter order stable.
                for key in sorted(inputs):
                    value = inputs[key]
                    if not isinstance(value, list):
                        continue
                    for item in value[1:]:
                        if isinstance(item, str) and item in blocks:
                            if not scan(item, stack | {bid}):
                                return False
            return True

        for bid in ids:
            if not scan(bid, frozenset()):
                return None
        return params

    def _extract_duplicates(self, blocks: dict) -> None:
        """Move repeated stacks into custom blocks when that makes them smaller.

        A repeated stack that uses definition arguments becomes a new custom
        block taking those arguments; callers pass the original argument
        reporters, so the values are unchanged.
        """
        st = self.stats
        # Keep the loop bounded: each successful pass strictly reduces the
        # target's block count, so it cannot run forever.  Failed attempts only
        # add their signature to ``banned``, so the bound also covers retries.
        banned = set()
        for _ in range(200):
            if self.cancelled():
                raise Cancelled()
            found = self._find_duplicate_group(blocks, banned)
            if not found:
                break
            starts, length, warp, params, sig = found
            before = copy.deepcopy(blocks)
            old_count = len(before)
            old_size = len(json.dumps(before, ensure_ascii=False,
                                      separators=(",", ":")))
            if not self._apply_duplicate_group(blocks, starts, length, warp,
                                               params):
                blocks.clear()
                blocks.update(before)
                banned.add(sig)
                continue
            new_count = len(blocks)
            new_size = len(json.dumps(blocks, ensure_ascii=False,
                                      separators=(",", ":")))
            if new_count >= old_count or new_size >= old_size:
                # This extraction is not profitable.  Remember it and try the
                # next-best candidate instead of giving up on the whole target.
                blocks.clear()
                blocks.update(before)
                banned.add(sig)
                continue
            st["duplicates_extracted"] += 1
            st["dup_blocks_saved"] += old_count - new_count

    def _find_duplicate_group(self, blocks: dict, banned=None):
        if not isinstance(blocks, dict):
            return None
        banned = banned or set()
        # There is no fixed minimum length: a candidate is accepted only when
        # the extraction actually makes the serialized blocks smaller, so even
        # a single (possibly nested) block can be worth sharing.  Short chains
        # are cheap to examine and rejected quickly unless they pay off.
        min_len = 1
        max_len = 100000
        canon_cache = {}

        def freeze(value):
            if isinstance(value, dict):
                return tuple(sorted((str(k), freeze(v)) for k, v in value.items()))
            if isinstance(value, list):
                return tuple(freeze(v) for v in value)
            return value

        def canon_input(value, stack):
            if not isinstance(value, list):
                return ("value", freeze(value))
            out = []
            for item in value:
                if isinstance(item, str) and item in blocks:
                    out.append(("ref", canon_block(item, True, stack)))
                elif isinstance(item, list):
                    out.append(("list", freeze(item)))
                else:
                    out.append(("value", item))
            return tuple(out)

        def canon_block(bid, include_next, stack=frozenset()):
            key = (bid, include_next)
            if key in canon_cache:
                return canon_cache[key]
            if bid in stack:
                return ("cycle",)
            blk = blocks.get(bid)
            if isinstance(blk, list):
                value = ("prim", freeze(blk))
                canon_cache[key] = value
                return value
            if not isinstance(blk, dict):
                value = ("missing",)
                canon_cache[key] = value
                return value
            nstack = stack | {bid}
            fields = tuple(sorted(
                (k, freeze(v)) for k, v in (blk.get("fields") or {}).items()))
            inputs = tuple(sorted(
                (k, canon_input(v, nstack))
                for k, v in (blk.get("inputs") or {}).items()))
            mutation = freeze(blk.get("mutation") or {})
            value = ("blk", blk.get("opcode"), fields, inputs, mutation,
                     bool(blk.get("shadow")))
            if include_next:
                nxt = blk.get("next")
                nval = (canon_block(nxt, True, nstack)
                        if isinstance(nxt, str) and nxt in blocks else None)
                value = value + (nval,)
            canon_cache[key] = value
            return value

        def seq_key(ids):
            return tuple(canon_block(bid, False) for bid in ids)

        param_cache = {}

        def chain_params(ids):
            ck = tuple(ids)
            if ck not in param_cache:
                param_cache[ck] = self._chain_argument_params(blocks, ids)
            return param_cache[ck]

        chain_cache = {}

        def chain_of(bid):
            ids = chain_cache.get(bid)
            if ids is None:
                ids = self._chain_ids(blocks, bid, max_len)
                chain_cache[bid] = ids
            return ids

        def common_length(a, b):
            ca = chain_of(a)
            cb = chain_of(b)
            n = 0
            for x, y in zip(ca, cb):
                if canon_block(x, False) != canon_block(y, False):
                    break
                n += 1
            return n, ca, cb

        groups = {}
        warp_bodies = set()
        owners = {}            # block id -> enclosing definition id
        owner_conflicts = set()
        def_argnames = {}      # definition id -> set of declared argument names
        for bid, blk in blocks.items():
            if not isinstance(blk, dict) or blk.get("opcode") != "procedures_definition":
                continue
            cb = (blk.get("inputs") or {}).get("custom_block")
            pid = cb[1] if isinstance(cb, list) and len(cb) > 1 else None
            proto = blocks.get(pid) if isinstance(pid, str) else None
            mut = (proto or {}).get("mutation") or {}
            try:
                names = json.loads(mut.get("argumentnames") or "[]")
            except (TypeError, ValueError):
                names = []
            if isinstance(names, list):
                def_argnames[bid] = {n for n in names if isinstance(n, str)}
            # Remember which definition owns each body block so a chain that
            # uses arguments is only moved when every occurrence is inside the
            # same definition (the call-site reporters then resolve to the same
            # values as the original body did).
            body = blk.get("next")
            if isinstance(body, str) and body in blocks:
                for cid in self._collect_subgraph(blocks, body, True):
                    if cid in owners and owners[cid] != bid:
                        owner_conflicts.add(cid)
                    else:
                        owners[cid] = bid
            # "Run without screen refresh" is a property of the enclosing
            # definition.  Moving part of a warp body into a non-warp
            # definition would change when the screen refreshes.
            if mut.get("warp") in (True, "true"):
                body = blk.get("next")
                if isinstance(body, str) and body in blocks:
                    warp_bodies |= self._collect_subgraph(blocks, body, True)
        for cid in owner_conflicts:
            owners.pop(cid, None)

        # A block referenced from a reporter input (VALUE, NUM1, CONDITION,
        # ...) is a reporter, not a stack.  It must never start a chain:
        # moving it into a custom-block body would turn it into a stacked
        # block and break script compilation.  Only SUBSTACK slots hold
        # stacked blocks.
        reporter_ids = set()
        for blk in blocks.values():
            if not isinstance(blk, dict):
                continue
            inputs = blk.get("inputs")
            if not isinstance(inputs, dict):
                continue
            for key, value in inputs.items():
                if (not isinstance(value, list) or len(value) < 2
                        or not isinstance(value[1], str)):
                    continue
                if key not in ("SUBSTACK", "SUBSTACK2"):
                    reporter_ids.add(value[1])
        for bid, blk in blocks.items():
            if not isinstance(blk, dict) or blk.get("shadow") is True:
                continue
            op = blk.get("opcode")
            if not isinstance(op, str) or op in EXTRACT_EXCLUDE_OPS:
                continue
            if op.startswith("argument_reporter"):
                continue
            if bid in reporter_ids:
                continue
            if self._is_hat_opcode(op):
                continue
            ids = self._chain_ids(blocks, bid, min_len)
            if len(ids) < min_len:
                continue
            # "Run without screen refresh" belongs to the enclosing custom
            # block.  Group by that context so a warp body is only ever moved
            # into another warp definition (and vice versa).
            context = bid in warp_bodies
            groups.setdefault((context, seq_key(ids)), []).append(bid)

        best = None  # (score, starts, length, warp, params, signature)
        for (context, sig), starts in groups.items():
            if len(starts) < 2:
                continue
            base = starts[0]
            pair_results = []
            for other in starts[1:]:
                length, ca, cb = common_length(base, other)
                if length < min_len:
                    continue
                # The two donor chains must not overlap.
                if set(ca[:length]) & set(cb[:length]):
                    continue
                pair_results.append((length, base, other))
            # Also try a non-first start as the anchor for repeated patterns.
            if len(starts) > 2:
                for i in range(1, min(len(starts), 8)):
                    for j in range(i + 1, min(len(starts), 12)):
                        length, ca, cb = common_length(starts[i], starts[j])
                        if length >= min_len and not (set(ca[:length]) & set(cb[:length])):
                            pair_results.append((length, starts[i], starts[j]))
            for length, a, b in pair_results:
                ids_a = self._chain_ids(blocks, a, length)
                ids_b = self._chain_ids(blocks, b, length)
                if len(ids_a) < length or len(ids_b) < length:
                    continue
                key = seq_key(ids_a)
                if key != seq_key(ids_b):
                    continue
                # Check the chain does not contain scope-sensitive stop
                # blocks or another definition/prototype.  Argument reporters
                # are allowed; they become parameters below.
                sub_a = set()
                for cid in ids_a:
                    sub_a |= self._collect_subgraph(blocks, cid, False)
                bad = False
                for cid in sub_a:
                    cb = blocks.get(cid)
                    if not isinstance(cb, dict):
                        continue
                    op = cb.get("opcode")
                    if (not isinstance(op, str)
                            or op in EXTRACT_FORBIDDEN_OPS
                            or self._is_hat_opcode(op)):
                        bad = True
                        break
                if bad:
                    continue

                params = chain_params(ids_a)
                if params is None:
                    continue
                owner = None
                if params:
                    # Argument values are fixed for the duration of one custom
                    # block call, so passing the original reporters at the call
                    # site is safe.  Requiring one owning definition also
                    # guarantees every call-site reporter resolves the same
                    # way the moved body did.
                    owner = owners.get(a)
                    if owner is None:
                        continue
                    known = def_argnames.get(owner, set())
                    if any(name not in known for name, _ in params):
                        continue

                # Pick all non-overlapping occurrences of the identical full
                # sequence.  Different continuations are fine: the call's next
                # pointer preserves them.
                selected = []
                used = set()
                for cand in starts:
                    cids = self._chain_ids(blocks, cand, length)
                    if len(cids) < length or seq_key(cids) != key:
                        continue
                    if params:
                        if owners.get(cand) != owner:
                            continue
                        if chain_params(cids) != params:
                            continue
                    csub = set()
                    for cid in cids:
                        csub |= self._collect_subgraph(blocks, cid, False)
                    if csub & used:
                        continue
                    selected.append(cand)
                    used |= csub
                if len(selected) < 2:
                    continue
                copy_blocks = set()
                for cid in self._chain_ids(blocks, selected[0], length):
                    copy_blocks |= self._collect_subgraph(blocks, cid, False)
                blocks_per_copy = len(copy_blocks)
                # A definition + prototype + one call per occurrence (with one
                # reporter per parameter) must be cheaper than the copies that
                # are removed.
                savings = ((len(selected) - 1) * blocks_per_copy
                           - len(selected) - 2
                           - len(selected) * len(params))
                if savings <= 0:
                    continue
                score = (savings, length, len(selected))
                cand_sig = (context, length, key)
                if cand_sig in banned:
                    continue
                if best is None or score > best[0]:
                    best = (score, selected, length, context, tuple(params),
                            cand_sig)
        if best is None:
            return None
        return best[1], best[2], best[3], list(best[4]), best[5]

    def _apply_duplicate_group(self, blocks: dict, starts, length: int,
                               warp: bool = False, params=()) -> bool:
        if len(starts) < 2:
            return False
        donor = starts[0]
        donor_ids = self._chain_ids(blocks, donor, length)
        if len(donor_ids) < length:
            return False
        infos = []
        for start in starts:
            ids = self._chain_ids(blocks, start, length)
            if len(ids) < length:
                return False
            first = blocks.get(start)
            last = blocks.get(ids[-1])
            if not isinstance(first, dict) or not isinstance(last, dict):
                return False
            prev = first.get("parent")
            cont = last.get("next")
            infos.append({
                "start": start,
                "ids": ids,
                "prev": prev if isinstance(prev, str) and prev in blocks else None,
                "cont": cont if isinstance(cont, str) and cont in blocks else None,
                "top": first.get("topLevel") is True,
                "x": first.get("x", 0),
                "y": first.get("y", 0),
            })

        # Reserve all new IDs up front.
        reserved = set(blocks)

        def new_id(prefix: str) -> str:
            i = 1
            while f"{prefix}{i}" in reserved:
                i += 1
            bid = f"{prefix}{i}"
            reserved.add(bid)
            return bid

        existing_codes = set()
        for blk in blocks.values():
            if not isinstance(blk, dict):
                continue
            if blk.get("opcode") in ("procedures_prototype", "procedures_call"):
                code = (blk.get("mutation") or {}).get("proccode")
                if isinstance(code, str):
                    existing_codes.add(code)
        n = 1
        while any(code == f"dup{n}" or code.startswith(f"dup{n} ")
                  for code in existing_codes):
            n += 1
        base_code = f"dup{n}"

        # Argument IDs must not collide with IDs of existing custom blocks.
        # They are independent from block IDs, so reserve both kinds.
        arg_reserved = set(reserved)
        for blk in blocks.values():
            if not isinstance(blk, dict):
                continue
            if blk.get("opcode") not in ("procedures_prototype",
                                         "procedures_call"):
                continue
            raw = (blk.get("mutation") or {}).get("argumentids")
            try:
                arg_ids = json.loads(raw) if isinstance(raw, str) else None
            except (TypeError, ValueError):
                arg_ids = None
            if isinstance(arg_ids, list):
                arg_reserved.update(a for a in arg_ids if isinstance(a, str))
        new_arg_ids = []
        arg_counter = 0
        for _name, _is_bool in params:
            while True:
                arg_counter += 1
                aid = f"arg{arg_counter}"
                if aid not in arg_reserved:
                    arg_reserved.add(aid)
                    break
            new_arg_ids.append(aid)

        placeholders = " ".join("%b" if is_bool else "%s"
                                for _name, is_bool in params)
        proccode = base_code + (f" {placeholders}" if placeholders else "")
        arg_ids_json = json.dumps(new_arg_ids, separators=(",", ":"))
        arg_names_json = json.dumps([name for name, _ in params],
                                    ensure_ascii=False,
                                    separators=(",", ":"))
        arg_defaults_json = json.dumps(
            [False if is_bool else "" for _name, is_bool in params],
            separators=(",", ":"))

        def_id = new_id("d")
        proto_id = new_id("p")
        call_ids = [new_id("c") for _ in infos]

        # Adjacent/embedded occurrences can have a predecessor that is part of
        # another extracted copy.  Redirect those links to the copy's call.
        owner_call = {}
        for info, call_id in zip(infos, call_ids):
            for cid in info["ids"]:
                owner_call.setdefault(cid, call_id)
                for sub in self._collect_subgraph(blocks, cid, False):
                    owner_call.setdefault(sub, call_id)

        # Move the first copy into the definition body.
        body_first = blocks[donor]
        body_first["parent"] = def_id
        body_first.pop("topLevel", None)
        body_first.pop("x", None)
        body_first.pop("y", None)
        blocks[donor_ids[-1]]["next"] = None

        blocks[def_id] = {
            "opcode": "procedures_definition",
            "next": donor,
            "parent": None,
            "inputs": {"custom_block": [1, proto_id]},
            "fields": {},
            "shadow": False,
            "topLevel": True,
            "x": 0,
            "y": 1000 + self.stats["duplicates_extracted"] * 100,
        }
        blocks[proto_id] = {
            "opcode": "procedures_prototype",
            "next": None,
            "parent": def_id,
            "inputs": {},
            "fields": {},
            "shadow": True,
            "topLevel": False,
            "mutation": {
                "tagName": "mutation",
                "children": [],
                "proccode": proccode,
                "argumentids": arg_ids_json,
                "argumentnames": arg_names_json,
                "argumentdefaults": arg_defaults_json,
                "warp": "true" if warp else "false",
            },
        }

        for info, call_id in zip(infos, call_ids):
            start = info["start"]
            prev = owner_call.get(info["prev"], info["prev"])
            cont = owner_call.get(info["cont"], info["cont"])
            if info is not infos[0]:
                sub = set()
                for cid in info["ids"]:
                    sub |= self._collect_subgraph(blocks, cid, False)
                for cid in sub:
                    blocks.pop(cid, None)
            # Re-create the arguments at this call site.  Argument values are
            # constant while the enclosing custom block runs, so evaluating
            # the same reporters here yields the same values as before.
            call_inputs = {}
            for aid, (arg_name, is_bool) in zip(new_arg_ids, params):
                reporter_id = new_id("r")
                blocks[reporter_id] = {
                    "opcode": ("argument_reporter_boolean" if is_bool
                               else "argument_reporter_string_number"),
                    "next": None,
                    "parent": call_id,
                    "inputs": {},
                    "fields": {"VALUE": [arg_name, None]},
                    "shadow": False,
                    "topLevel": False,
                }
                if is_bool:
                    # Boolean inputs have no shadow block.
                    call_inputs[aid] = [2, reporter_id]
                else:
                    call_inputs[aid] = [3, reporter_id, [10, ""]]
            call = {
                "opcode": "procedures_call",
                "next": cont,
                "parent": prev,
                "inputs": call_inputs,
                "fields": {},
                "shadow": False,
                "topLevel": bool(info["top"] and prev is None),
                "mutation": {
                    "tagName": "mutation",
                    "children": [],
                    "proccode": proccode,
                    "argumentids": arg_ids_json,
                    "warp": "true" if warp else "false",
                },
            }
            if call["topLevel"]:
                call["x"] = info["x"]
                call["y"] = info["y"]
            blocks[call_id] = call
            if prev is not None and prev in blocks:
                parent = blocks[prev]
                replaced = False
                if isinstance(parent, dict):
                    if parent.get("next") == start:
                        parent["next"] = call_id
                        replaced = True
                    elif parent.get("next") == call_id:
                        replaced = True
                    inputs = parent.get("inputs")
                    if not replaced and isinstance(inputs, dict):
                        for key, value in inputs.items():
                            if not isinstance(value, list):
                                continue
                            for i, item in enumerate(value):
                                if i > 0 and item == start:
                                    value[i] = call_id
                                    replaced = True
                if not replaced:
                    call["parent"] = None
                    call["topLevel"] = True
            if (cont is not None and cont in blocks
                    and cont not in owner_call):
                blocks[cont]["parent"] = call_id

        return True

    @staticmethod
    def _near_hole(entry):
        """Return ``(type, value)`` when an input is a plain literal.

        Only slots that are represented by a literal shadow with no block
        behind it can be replaced by a custom-block argument.  Dropdown
        ``fields`` are deliberately not handled: they are not inputs, so
        Scratch never evaluates a reporter there.
        """
        if (isinstance(entry, list) and len(entry) == 2 and entry[0] == 1
                and isinstance(entry[1], list) and len(entry[1]) >= 2
                and entry[1][0] in LITERAL_PRIMITIVE_TYPES):
            return entry[1][0], entry[1][1]
        return None

    def _near_canon(self, blocks: dict, bid: str, cache=None):
        """Return a literal-wildcard signature plus the wildcard slots.

        Two blocks with the same signature have the same opcode, fields,
        mutation and reporter shape; they may differ only in literal input
        values.  ``holes`` holds ``(parent_id, entry, type, value)`` tuples
        in a deterministic order, where ``entry`` is the live input list so
        the caller can replace it with an argument reporter.
        """
        if cache is None:
            cache = {}

        def freeze(value):
            if isinstance(value, dict):
                return tuple(sorted((str(k), freeze(v))
                                    for k, v in value.items()))
            if isinstance(value, list):
                return tuple(freeze(v) for v in value)
            return value

        def canon(current, stack):
            if current in cache:
                return cache[current]
            if current in stack:
                return (("cycle",), [])
            blk = blocks.get(current)
            if isinstance(blk, list):
                value = (("prim", freeze(blk)), [])
                cache[current] = value
                return value
            if not isinstance(blk, dict):
                value = (("missing",), [])
                cache[current] = value
                return value
            nstack = stack | {current}
            fields = tuple(sorted(
                (k, freeze(v)) for k, v in (blk.get("fields") or {}).items()))
            holes = []
            inputs = []
            for key in sorted((blk.get("inputs") or {})):
                entry = blk["inputs"][key]
                hole = self._near_hole(entry)
                if hole is not None:
                    holes.append((current, entry, hole[0], hole[1]))
                    inputs.append((key, ("literal",)))
                    continue
                if not isinstance(entry, list):
                    inputs.append((key, ("value", freeze(entry))))
                    continue
                parts = []
                for item in entry:
                    if isinstance(item, str) and item in blocks:
                        child_sig, child_holes = canon(item, nstack)
                        parts.append(("ref", child_sig))
                        holes.extend(child_holes)
                    elif isinstance(item, list):
                        parts.append(("list", freeze(item)))
                    else:
                        parts.append(("value", item))
                inputs.append((key, tuple(parts)))
            value = (
                ("blk", blk.get("opcode"), fields, tuple(inputs),
                 freeze(blk.get("mutation") or {}), bool(blk.get("shadow"))),
                holes,
            )
            cache[current] = value
            return value

        return canon(bid, frozenset())

    def _extract_near_duplicates(self, blocks: dict) -> None:
        """Share single-block patterns whose literals differ.

        The differing literal slots become custom-block arguments; every
        other part of the pattern (including dropdown fields) must match
        exactly.  A group is only applied when both the block count and the
        serialized size shrink, so the result is always smaller.
        """
        st = self.stats
        banned = set()
        for _ in range(200):
            if self.cancelled():
                raise Cancelled()
            found = self._find_near_duplicate_group(blocks, banned)
            if not found:
                break
            starts, diff_idx, params, warp, sig = found
            before = copy.deepcopy(blocks)
            old_count = len(before)
            old_size = len(json.dumps(before, ensure_ascii=False,
                                      separators=(",", ":")))
            if not self._apply_near_duplicate_group(
                    blocks, starts, diff_idx, params, warp):
                blocks.clear()
                blocks.update(before)
                banned.add(sig)
                continue
            new_count = len(blocks)
            new_size = len(json.dumps(blocks, ensure_ascii=False,
                                      separators=(",", ":")))
            if new_count >= old_count or new_size >= old_size:
                blocks.clear()
                blocks.update(before)
                banned.add(sig)
                continue
            st["near_duplicates_extracted"] += 1
            st["near_blocks_saved"] += old_count - new_count

    def _find_near_duplicate_group(self, blocks: dict, banned=None):
        if not isinstance(blocks, dict):
            return None
        banned = banned or set()
        cache = {}

        warp_bodies = set()
        owners = {}
        owner_conflicts = set()
        def_argnames = {}
        for bid, blk in blocks.items():
            if not isinstance(blk, dict) or blk.get("opcode") != "procedures_definition":
                continue
            cb = (blk.get("inputs") or {}).get("custom_block")
            pid = cb[1] if isinstance(cb, list) and len(cb) > 1 else None
            proto = blocks.get(pid) if isinstance(pid, str) else None
            mut = (proto or {}).get("mutation") or {}
            try:
                names = json.loads(mut.get("argumentnames") or "[]")
            except (TypeError, ValueError):
                names = []
            if isinstance(names, list):
                def_argnames[bid] = {n for n in names if isinstance(n, str)}
            body = blk.get("next")
            if isinstance(body, str) and body in blocks:
                for cid in self._collect_subgraph(blocks, body, True):
                    if cid in owners and owners[cid] != bid:
                        owner_conflicts.add(cid)
                    else:
                        owners[cid] = bid
            if mut.get("warp") in (True, "true"):
                body = blk.get("next")
                if isinstance(body, str) and body in blocks:
                    warp_bodies |= self._collect_subgraph(blocks, body, True)
        for cid in owner_conflicts:
            owners.pop(cid, None)

        # A block referenced from a reporter input is never a stack candidate;
        # only SUBSTACK slots can hold stacked blocks.
        reporter_ids = set()
        for blk in blocks.values():
            if not isinstance(blk, dict):
                continue
            inputs = blk.get("inputs")
            if not isinstance(inputs, dict):
                continue
            for key, value in inputs.items():
                if (not isinstance(value, list) or len(value) < 2
                        or not isinstance(value[1], str)):
                    continue
                if key not in ("SUBSTACK", "SUBSTACK2"):
                    reporter_ids.add(value[1])

        groups = {}
        for bid, blk in blocks.items():
            if not isinstance(blk, dict) or blk.get("shadow") is True:
                continue
            op = blk.get("opcode")
            if not isinstance(op, str) or op in EXTRACT_EXCLUDE_OPS:
                continue
            if op.startswith("argument_reporter"):
                continue
            if bid in reporter_ids:
                continue
            if self._is_hat_opcode(op):
                continue
            sig, holes = self._near_canon(blocks, bid, cache)
            if not holes:
                # Identical subtrees are handled by _extract_duplicates.
                continue
            context = bid in warp_bodies
            groups.setdefault((context, sig), []).append(bid)

        best = None
        for (context, sig), starts in groups.items():
            if len(starts) < 2 or (context, sig) in banned:
                continue
            # Pick non-overlapping occurrences.  A control block's subgraph
            # includes its substacks, so nested occurrences are skipped.
            selected = []
            used = set()
            info = []
            for cand in starts:
                sub = self._collect_subgraph(blocks, cand, False)
                if sub & used:
                    continue
                selected.append(cand)
                used |= sub
                info.append((cand, sub))
            if len(selected) < 2:
                continue

            base = selected[0]
            params = self._chain_argument_params(blocks, [base])
            if params is None:
                continue
            if params:
                # Existing definition arguments are passed through as
                # reporters, so every occurrence must live in the same
                # definition (same values at every call site).
                owner = owners.get(base)
                if owner is None:
                    continue
                known = def_argnames.get(owner, set())
                if any(name not in known for name, _ in params):
                    continue
                if any(owners.get(cand) != owner for cand in selected):
                    continue

            hole_lists = [self._near_canon(blocks, cand, cache)[1]
                          for cand in selected]
            count = len(hole_lists[0])
            if any(len(h) != count for h in hole_lists):
                continue
            diff_idx = []
            for i in range(count):
                values = {(h[i][2], h[i][3]) for h in hole_lists}
                if len(values) > 1:
                    diff_idx.append(i)
            if not diff_idx:
                # Same literals everywhere; the exact pass owns this pattern.
                continue

            size = len(info[0][1])
            n = len(selected)
            savings = ((n - 1) * size
                       - (2 + n + n * len(params) + len(diff_idx)))
            if savings <= 0:
                continue
            score = (savings, size, n)
            if best is None or score > best[0]:
                best = (score, selected, diff_idx, list(params), context,
                        (context, sig))
        if best is None:
            return None
        return best[1], best[2], best[3], best[4], best[5]

    def _apply_near_duplicate_group(self, blocks: dict, starts, diff_idx,
                                    params, warp: bool = False) -> bool:
        if len(starts) < 2:
            return False
        infos = []
        cache = {}
        for start in starts:
            blk = blocks.get(start)
            if not isinstance(blk, dict):
                return False
            sig, holes = self._near_canon(blocks, start, cache)
            if len(holes) < max(diff_idx, default=-1) + 1:
                return False
            infos.append({
                "start": start,
                "sub": self._collect_subgraph(blocks, start, False),
                "holes": holes,
                "prev": (blk.get("parent") if isinstance(blk.get("parent"), str)
                         and blk.get("parent") in blocks else None),
                "cont": (blk.get("next") if isinstance(blk.get("next"), str)
                         and blk.get("next") in blocks else None),
                "top": blk.get("topLevel") is True,
                "x": blk.get("x", 0),
                "y": blk.get("y", 0),
            })

        reserved = set(blocks)

        def new_id(prefix: str) -> str:
            i = 1
            while f"{prefix}{i}" in reserved:
                i += 1
            bid = f"{prefix}{i}"
            reserved.add(bid)
            return bid

        existing_codes = set()
        arg_reserved = set(reserved)
        for blk in blocks.values():
            if not isinstance(blk, dict):
                continue
            if blk.get("opcode") not in ("procedures_prototype",
                                         "procedures_call"):
                continue
            mut = blk.get("mutation") or {}
            code = mut.get("proccode")
            if isinstance(code, str):
                existing_codes.add(code)
            raw = mut.get("argumentids")
            try:
                arg_ids = json.loads(raw) if isinstance(raw, str) else None
            except (TypeError, ValueError):
                arg_ids = None
            if isinstance(arg_ids, list):
                arg_reserved.update(a for a in arg_ids if isinstance(a, str))

        n = 1
        while any(code == f"ndup{n}" or code.startswith(f"ndup{n} ")
                  for code in existing_codes):
            n += 1
        base_code = f"ndup{n}"

        used_names = {name for name, _ in params}
        lit_names = []
        k = 0
        while len(lit_names) < len(diff_idx):
            k += 1
            name = f"p{k}"
            if name not in used_names:
                used_names.add(name)
                lit_names.append(name)
        all_params = list(params) + [(name, False) for name in lit_names]

        new_arg_ids = []
        arg_counter = 0
        for _name, _is_bool in all_params:
            while True:
                arg_counter += 1
                aid = f"arg{arg_counter}"
                if aid not in arg_reserved:
                    arg_reserved.add(aid)
                    break
            new_arg_ids.append(aid)

        placeholders = " ".join("%b" if is_bool else "%s"
                                for _name, is_bool in all_params)
        proccode = base_code + (f" {placeholders}" if placeholders else "")
        arg_ids_json = json.dumps(new_arg_ids, separators=(",", ":"))
        arg_names_json = json.dumps([name for name, _ in all_params],
                                    ensure_ascii=False,
                                    separators=(",", ":"))
        arg_defaults_json = json.dumps(
            [False if is_bool else "" for _name, is_bool in all_params],
            separators=(",", ":"))

        def_id = new_id("d")
        proto_id = new_id("p")
        call_ids = [new_id("c") for _ in infos]
        body_reporter_ids = [new_id("r") for _ in diff_idx]
        call_reporter_ids = [[new_id("r") for _ in params] for _ in infos]

        # Turn the first copy into the definition body.
        donor = starts[0]
        body = blocks[donor]
        body["parent"] = def_id
        body.pop("topLevel", None)
        body.pop("x", None)
        body.pop("y", None)
        body["next"] = None
        for j, (hole_idx, rid) in enumerate(zip(diff_idx, body_reporter_ids)):
            parent_id, entry, _lit_type, _lit_value = infos[0]["holes"][hole_idx]
            blocks[rid] = {
                "opcode": "argument_reporter_string_number",
                "next": None,
                "parent": parent_id,
                "inputs": {},
                "fields": {"VALUE": [lit_names[j], None]},
                "shadow": False,
                "topLevel": False,
            }
            entry[:] = [2, rid]

        blocks[def_id] = {
            "opcode": "procedures_definition",
            "next": donor,
            "parent": None,
            "inputs": {"custom_block": [1, proto_id]},
            "fields": {},
            "shadow": False,
            "topLevel": True,
            "x": 0,
            "y": 1000 + (self.stats["duplicates_extracted"]
                         + self.stats["near_duplicates_extracted"]) * 100,
        }
        blocks[proto_id] = {
            "opcode": "procedures_prototype",
            "next": None,
            "parent": def_id,
            "inputs": {},
            "fields": {},
            "shadow": True,
            "topLevel": False,
            "mutation": {
                "tagName": "mutation",
                "children": [],
                "proccode": proccode,
                "argumentids": arg_ids_json,
                "argumentnames": arg_names_json,
                "argumentdefaults": arg_defaults_json,
                "warp": "true" if warp else "false",
            },
        }

        # Create every call before linking: adjacent occurrences may point at
        # each other, and both call blocks must exist by then.
        for info, call_id, reporter_ids in zip(infos, call_ids,
                                               call_reporter_ids):
            call_inputs = {}
            for k, (arg_name, is_bool) in enumerate(params):
                rid = reporter_ids[k]
                blocks[rid] = {
                    "opcode": ("argument_reporter_boolean" if is_bool
                               else "argument_reporter_string_number"),
                    "next": None,
                    "parent": call_id,
                    "inputs": {},
                    "fields": {"VALUE": [arg_name, None]},
                    "shadow": False,
                    "topLevel": False,
                }
                aid = new_arg_ids[k]
                if is_bool:
                    call_inputs[aid] = [2, rid]
                else:
                    call_inputs[aid] = [3, rid, [10, ""]]
            for j, aid in enumerate(new_arg_ids[len(params):]):
                _parent, _entry, lit_type, lit_value = info["holes"][diff_idx[j]]
                call_inputs[aid] = [1, [lit_type, lit_value]]
            blocks[call_id] = {
                "opcode": "procedures_call",
                "next": None,
                "parent": None,
                "inputs": call_inputs,
                "fields": {},
                "shadow": False,
                "topLevel": False,
                "mutation": {
                    "tagName": "mutation",
                    "children": [],
                    "proccode": proccode,
                    "argumentids": arg_ids_json,
                    "warp": "true" if warp else "false",
                },
            }

        owner_call = {}
        for info, call_id in zip(infos, call_ids):
            for cid in info["sub"]:
                owner_call.setdefault(cid, call_id)

        # Remove the copies that are replaced by calls; the donor lives on as
        # the definition body.
        for info in infos[1:]:
            for cid in info["sub"]:
                blocks.pop(cid, None)

        for info, call_id in zip(infos, call_ids):
            start = info["start"]
            prev = owner_call.get(info["prev"], info["prev"])
            cont = owner_call.get(info["cont"], info["cont"])
            call = blocks[call_id]
            call["next"] = cont
            call["parent"] = prev
            if info["top"] and prev is None:
                call["topLevel"] = True
                call["x"] = info["x"]
                call["y"] = info["y"]
            if prev is not None and prev in blocks:
                parent = blocks[prev]
                replaced = False
                if isinstance(parent, dict):
                    if parent.get("next") == start:
                        parent["next"] = call_id
                        replaced = True
                    elif parent.get("next") == call_id:
                        replaced = True
                    inputs = parent.get("inputs")
                    if not replaced and isinstance(inputs, dict):
                        for value in inputs.values():
                            if not isinstance(value, list):
                                continue
                            for i, item in enumerate(value):
                                if i > 0 and item == start:
                                    value[i] = call_id
                                    replaced = True
                if not replaced:
                    call["parent"] = None
                    call["topLevel"] = True
            if cont is not None and cont in blocks and cont not in owner_call:
                blocks[cont]["parent"] = call_id

        return True

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
        # Reserve every existing proccode (including calls whose definition is
        # missing) so a generated short name cannot bind to an orphan call.
        used_new = set(retained)
        for p in protos.values():
            code = ((p.get("mutation") or {}).get("proccode")
                    if isinstance(p, dict) else None)
            if isinstance(code, str):
                used_new.add(code)
        for b in calls:
            code = ((b.get("mutation") or {}).get("proccode")
                    if isinstance(b, dict) else None)
            if isinstance(code, str):
                used_new.add(code)
        i = 0
        for old, grp in groups.items():
            if len(grp) > 1:
                continue
            placeholders = proccode_placeholders(old)
            suffix = (" " + " ".join(placeholders)) if placeholders else ""
            while True:
                i += 1
                cand = encode_id(i)
                new_code = cand + suffix
                if new_code not in used_new and new_code != old:
                    break
            used_new.add(new_code)
            proc_map[old] = new_code
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

    def _normalize_parent_markers(self, blocks: dict) -> None:
        """Keep ``topLevel``/workspace coordinates only on real root blocks.

        Extraction passes can first mark a replacement call as top-level and
        later splice it into a stack.  If the stale marker is left behind, the
        editor sees a block that is both top-level and a child, which is an
        inconsistent project structure.
        """
        for blk in blocks.values():
            if not isinstance(blk, dict) or blk.get("parent") is None:
                continue
            blk.pop("topLevel", None)
            blk.pop("x", None)
            blk.pop("y", None)

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
        kept_mons = []
        for mon in mons:
            if not isinstance(mon, dict):
                kept_mons.append(mon)
                continue
            op = mon.get("opcode")
            if op in ("data_variable", "data_listcontents"):
                mid = mon.get("id")
                if op == "data_variable":
                    table, byname = self.var_map, self.var_name_ids
                    dropped = self._dropped_var_ids
                    pkey = "VARIABLE"
                else:
                    table, byname = self.list_map, self.list_name_ids
                    dropped = self._dropped_list_ids
                    pkey = "LIST"
                pname = (mon.get("params") or {}).get(pkey)
                if isinstance(mid, str) and mid in dropped:
                    continue
                if (not isinstance(mid, str) or mid not in table) and pname is not None:
                    ids = byname.get(pname, set())
                    if ids and ids <= dropped:
                        continue
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
            kept_mons.append(mon)
        project["monitors"] = kept_mons
        if not kept_mons:
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
    print(f"         unreachable blocks {st['unreachable_blocks_removed']} / "
          f"comments {st['unreachable_comments_removed']} / "
          f"broadcasts {st['broadcasts_removed']} / "
          f"obscured defaults {st['obscured_shadows_removed']}")
    print(f"         initial values cleared {st['vars_initialized'] + st['lists_initialized']} / "
          f"duplicate groups {st['duplicates_extracted']} "
          f"({st['dup_blocks_saved']} blocks saved) / "
          f"near-duplicates {st['near_duplicates_extracted']} "
          f"({st['near_blocks_saved']} blocks saved)")
    print(f"         loops {st['loops_created']} ({st['loop_blocks_saved']} blocks saved) / "
          f"defs inlined {st['procs_inlined']} / folded values {st['const_values_folded']} / "
          f"constant vars {st['const_vars_inlined']} "
          f"({st['const_reads_inlined']} reads)")
    print(f"         no-op defs {st['noop_procs_removed']} / no-op messages "
          f"{st['noop_broadcasts_removed']} / if-else simplified "
          f"{st['ifelse_converted']}")
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
            root.geometry("760x780")
            root.minsize(640, 620)

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
            self.opt_shadows = tk.BooleanVar(value=True)
            self.opt_unreachable = tk.BooleanVar(value=True)
            self.opt_init = tk.BooleanVar(value=True)
            self.opt_dup = tk.BooleanVar(value=True)
            self.opt_neardup = tk.BooleanVar(value=True)
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
            ttk.Checkbutton(fopt, variable=self.opt_shadows,
                            text="Remove input defaults hidden under reporter blocks"
                            ).grid(row=6, column=0, sticky="w")
            ttk.Checkbutton(fopt, variable=self.opt_unreachable,
                            text="Remove unreachable blocks, comments, definitions, and messages"
                            ).grid(row=7, column=0, sticky="w")
            ttk.Checkbutton(fopt, variable=self.opt_init,
                            text="Blank initial values that are always overwritten first"
                            ).grid(row=8, column=0, sticky="w")
            ttk.Checkbutton(fopt, variable=self.opt_dup,
                            text="Extract repeated code into custom blocks"
                            ).grid(row=9, column=0, sticky="w")
            ttk.Checkbutton(fopt, variable=self.opt_neardup,
                            text="Share near-duplicates by passing differing literals as arguments"
                            ).grid(row=10, column=0, sticky="w")

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
                           freq_ids=self.opt_freq.get(),
                           drop_obscured_shadows=self.opt_shadows.get(),
                           remove_unreachable=self.opt_unreachable.get(),
                           clear_initial_values=self.opt_init.get(),
                           extract_duplicates=self.opt_dup.get(),
                           near_duplicates=self.opt_neardup.get())
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
                f"Custom blocks shortened {st['procs_renamed']}\n"
                f"Unreachable blocks {st['unreachable_blocks_removed']} / "
                f"comments {st['unreachable_comments_removed']} / "
                f"messages {st['broadcasts_removed']} / "
                f"hidden defaults {st['obscured_shadows_removed']}\n"
                f"Initial values cleared {st['vars_initialized'] + st['lists_initialized']} / "
                f"duplicate groups {st['duplicates_extracted']} "
                f"({st['dup_blocks_saved']} blocks saved) / "
                f"near-duplicates {st['near_duplicates_extracted']} "
                f"({st['near_blocks_saved']} blocks saved)\n"
                f"Loops {st['loops_created']} ({st['loop_blocks_saved']} blocks saved) / "
                f"defs inlined {st['procs_inlined']} / "
                f"folded values {st['const_values_folded']} / "
                f"constant vars {st['const_vars_inlined']} "
                f"({st['const_reads_inlined']} reads)\n"
                f"No-op defs {st['noop_procs_removed']} / no-op messages "
                f"{st['noop_broadcasts_removed']} / if-else simplified "
                f"{st['ifelse_converted']}")
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

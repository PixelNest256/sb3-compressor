# -*- coding: utf-8 -*-
"""Stricter, invariant-oriented tests for sb3_compressor.py.

The normal test suite checks individual features.  This suite additionally
checks structural invariants on every produced project, determinism, and a
seeded fuzz corpus.  It is intentionally independent of the normal test file
except for its builders.
"""
import copy
import json
import os
import random
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sb3_compressor import Compressor, Options, load_input
from test_sb3_compressor import (build_argument_duplicate_sample,
                                 build_near_duplicate_sample,
                                 build_warp_duplicate_sample)


# ---------------------------------------------------------------------------
# Strict structural validator
# ---------------------------------------------------------------------------
def _parse_json_list(raw, label, errors):
    if not isinstance(raw, str):
        errors.append(f"{label}: missing JSON list")
        return []
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        errors.append(f"{label}: invalid JSON {raw!r}")
        return []
    if not isinstance(value, list):
        errors.append(f"{label}: not a list")
        return []
    return value


def _primitive_errors(prim, where, var_ids, list_ids, bc_ids, bc_by_id, errors):
    if not isinstance(prim, list) or not prim:
        errors.append(f"{where}: empty primitive")
        return
    typ = prim[0]
    if typ in (4, 5, 6, 7, 8):
        # Numeric primitives are editor hints, not value constraints: Scratch
        # stores values such as "last" and "random" in numeric slots too.
        if len(prim) < 2:
            errors.append(f"{where}: numeric primitive has no value")
    elif typ == 9:
        if len(prim) < 2 or not isinstance(prim[1], str):
            errors.append(f"{where}: bad colour primitive")
    elif typ == 10:
        if len(prim) < 2:
            errors.append(f"{where}: text primitive has no value")
    elif typ == 11:
        if len(prim) < 3:
            errors.append(f"{where}: broadcast primitive is incomplete")
            return
        name, bid = prim[1], prim[2]
        if bid not in bc_ids:
            errors.append(f"{where}: unknown broadcast id {bid!r}")
        elif bc_by_id.get(bid) != name:
            errors.append(f"{where}: broadcast name/id mismatch")
    elif typ == 12:
        if len(prim) < 3 or prim[2] not in var_ids:
            errors.append(f"{where}: unknown variable id {prim[2] if len(prim) > 2 else None!r}")
    elif typ == 13:
        if len(prim) < 3 or prim[2] not in list_ids:
            errors.append(f"{where}: unknown list id {prim[2] if len(prim) > 2 else None!r}")
    else:
        errors.append(f"{where}: unknown primitive type {typ!r}")


def _proccode_arity(code, errors, where):
    count = 0
    i = 0
    while i < len(code):
        ch = code[i]
        if ch == "%":
            if i + 1 >= len(code):
                errors.append(f"{where}: dangling % in proccode")
                break
            nxt = code[i + 1]
            if nxt == "%":
                i += 2
                continue
            if nxt in ("s", "b"):
                count += 1
                i += 2
                continue
            errors.append(f"{where}: unknown placeholder %{nxt} in proccode")
        i += 1
    return count


def validate_strict(project, allow_undeclared_args=False):
    """Return a list of structural/reference errors (empty means healthy).

    ``allow_undeclared_args`` tolerates legacy projects that already contain
    argument reporter blocks outside their definition.  Such projects load in
    TurboWarp, but new/generated output should be checked with the default
    strict setting.
    """
    errors = []
    targets = project.get("targets")
    if not isinstance(targets, list) or not targets:
        return ["targets is missing or empty"]
    if not any(isinstance(t, dict) and t.get("isStage") for t in targets):
        errors.append("no stage target")

    var_ids, list_ids, bc_ids = {}, {}, {}
    bc_by_id = {}
    for t in targets:
        if not isinstance(t, dict):
            errors.append("target is not an object")
            continue
        tname = t.get("name")
        for vid, ent in (t.get("variables") or {}).items():
            if not isinstance(vid, str) or not vid:
                errors.append(f"{tname}: bad variable key {vid!r}")
            if not isinstance(ent, list) or len(ent) < 1 or not isinstance(ent[0], str):
                errors.append(f"{tname}: bad variable entry for {vid!r}")
            var_ids[vid] = ent
        for lid, ent in (t.get("lists") or {}).items():
            if not isinstance(lid, str) or not lid:
                errors.append(f"{tname}: bad list key {lid!r}")
            if not isinstance(ent, list) or len(ent) < 1 or not isinstance(ent[0], str):
                errors.append(f"{tname}: bad list entry for {lid!r}")
            list_ids[lid] = ent
        for bid, ent in (t.get("broadcasts") or {}).items():
            if not isinstance(bid, str) or not bid:
                errors.append(f"{tname}: bad broadcast key {bid!r}")
            name = ent[0] if isinstance(ent, list) and ent else ent
            if not isinstance(name, str):
                errors.append(f"{tname}: bad broadcast entry for {bid!r}")
            bc_ids[bid] = name
            bc_by_id[bid] = name
        if t.get("isStage") and not t.get("name"):
            errors.append("stage has no name")

    for t in targets:
        if not isinstance(t, dict):
            continue
        tname = t.get("name")
        blocks = t.get("blocks")
        if not isinstance(blocks, dict):
            errors.append(f"{tname}: blocks is not an object")
            continue
        ids = set(blocks)
        for bid, b in blocks.items():
            if isinstance(b, list):
                _primitive_errors(b, f"{tname}.{bid}", var_ids, list_ids,
                                  bc_ids, bc_by_id, errors)
                continue
            if not isinstance(b, dict):
                errors.append(f"{tname}.{bid}: block is not an object")
                continue
            op = b.get("opcode")
            if not isinstance(op, str) or not op:
                errors.append(f"{tname}.{bid}: missing opcode")
            if "parent" not in b:
                errors.append(f"{tname}.{bid}: missing parent key")
            if "next" not in b:
                errors.append(f"{tname}.{bid}: missing next key")
            parent = b.get("parent")
            nxt = b.get("next")
            top = b.get("topLevel") is True
            shadow = b.get("shadow") is True

            if top and parent not in (None,):
                errors.append(f"{tname}.{bid}: topLevel block has a parent")
            if parent is not None:
                if parent not in ids:
                    errors.append(f"{tname}.{bid}: dangling parent {parent!r}")
                else:
                    pb = blocks[parent]
                    if not isinstance(pb, dict):
                        errors.append(f"{tname}.{bid}: parent is not a block")
                    else:
                        linked = pb.get("next") == bid
                        if not linked:
                            for value in (pb.get("inputs") or {}).values():
                                if isinstance(value, list) and any(
                                        item == bid for item in value[1:]):
                                    linked = True
                                    break
                        if not linked:
                            errors.append(
                                f"{tname}.{bid}: parent {parent} does not reference it")
            if nxt is not None:
                if nxt not in ids:
                    errors.append(f"{tname}.{bid}: dangling next {nxt!r}")
                else:
                    nb = blocks[nxt]
                    if not isinstance(nb, dict):
                        errors.append(f"{tname}.{bid}: next is not a block")
                    elif nb.get("parent") != bid:
                        errors.append(f"{tname}.{bid}: next {nxt} has wrong parent")
                    elif nb.get("shadow") is True:
                        errors.append(f"{tname}.{bid}: next points at a shadow block")

            inputs = b.get("inputs")
            if inputs is not None and not isinstance(inputs, dict):
                errors.append(f"{tname}.{bid}: inputs is not an object")
                inputs = {}
            for key, value in (inputs or {}).items():
                if not isinstance(value, list) or len(value) < 2:
                    errors.append(f"{tname}.{bid}.{key}: bad input entry")
                    continue
                tag = value[0]
                if tag not in (1, 2, 3):
                    errors.append(f"{tname}.{bid}.{key}: bad input tag {tag!r}")
                if tag == 1 and len(value) > 2:
                    errors.append(f"{tname}.{bid}.{key}: tag 1 has a shadow")
                if tag == 3 and len(value) != 3:
                    errors.append(f"{tname}.{bid}.{key}: tag 3 must have 3 items")
                for index, item in enumerate(value[1:], 1):
                    if isinstance(item, str):
                        if item not in ids:
                            errors.append(
                                f"{tname}.{bid}.{key}: dangling block ref {item!r}")
                        elif index == 1:
                            rb = blocks[item]
                            if isinstance(rb, dict) and rb.get("parent") != bid:
                                errors.append(
                                    f"{tname}.{bid}.{key}: child {item} has wrong parent")
                    elif isinstance(item, list):
                        _primitive_errors(item, f"{tname}.{bid}.{key}",
                                          var_ids, list_ids, bc_ids,
                                          bc_by_id, errors)
                    else:
                        errors.append(f"{tname}.{bid}.{key}: bad item {item!r}")

            fields = b.get("fields")
            if fields is not None and not isinstance(fields, dict):
                errors.append(f"{tname}.{bid}: fields is not an object")
                fields = {}
            for key, fv in (fields or {}).items():
                if not isinstance(fv, list) or not fv:
                    errors.append(f"{tname}.{bid}.{key}: bad field entry")
                    continue
                fid = fv[1] if len(fv) > 1 else None
                if key == "VARIABLE" and fid is not None and fid not in var_ids:
                    errors.append(f"{tname}.{bid}.{key}: unknown variable {fid!r}")
                elif key == "LIST" and fid is not None and fid not in list_ids:
                    errors.append(f"{tname}.{bid}.{key}: unknown list {fid!r}")
                elif key == "BROADCAST_OPTION" and fid is not None and fid not in bc_ids:
                    errors.append(f"{tname}.{bid}.{key}: unknown broadcast {fid!r}")

        # ---- procedures ----
        protos = {}
        defs = []
        calls = []
        arg_reporters = []
        for bid, b in blocks.items():
            if not isinstance(b, dict):
                continue
            op = b.get("opcode")
            if op == "procedures_prototype":
                mut = b.get("mutation") or {}
                code = mut.get("proccode")
                if not isinstance(code, str) or not code:
                    errors.append(f"{tname}.{bid}: prototype without proccode")
                    continue
                aids = _parse_json_list(mut.get("argumentids"),
                                        f"{tname}.{bid}.argumentids", errors)
                names = _parse_json_list(mut.get("argumentnames"),
                                         f"{tname}.{bid}.argumentnames", errors)
                defaults = _parse_json_list(mut.get("argumentdefaults"),
                                            f"{tname}.{bid}.argumentdefaults", errors)
                if not (len(aids) == len(names) == len(defaults)):
                    errors.append(f"{tname}.{bid}: argument list lengths differ")
                if len(set(aids)) != len(aids):
                    errors.append(f"{tname}.{bid}: duplicate argument ids")
                if len(set(names)) != len(names):
                    errors.append(f"{tname}.{bid}: duplicate argument names")
                if any(not isinstance(a, str) or not a for a in aids):
                    errors.append(f"{tname}.{bid}: bad argument id")
                if any(not isinstance(n, str) or not n for n in names):
                    errors.append(f"{tname}.{bid}: bad argument name")
                arity = _proccode_arity(code, errors, f"{tname}.{bid}")
                if arity != len(names):
                    errors.append(
                        f"{tname}.{bid}: proccode arity {arity} != {len(names)}")
                protos[bid] = {
                    "code": code, "aids": aids, "names": names,
                    "defaults": defaults,
                    "warp": str(mut.get("warp", "false")).lower() == "true",
                }
            elif op == "procedures_definition":
                defs.append(bid)
            elif op == "procedures_call":
                calls.append(bid)
            elif isinstance(op, str) and op.startswith("argument_reporter"):
                arg_reporters.append(bid)

        referenced = set()
        for did in defs:
            b = blocks[did]
            cb = (b.get("inputs") or {}).get("custom_block")
            if not isinstance(cb, list) or len(cb) < 2 or not isinstance(cb[1], str):
                errors.append(f"{tname}.{did}: definition has no prototype")
                continue
            pid = cb[1]
            if pid not in protos:
                errors.append(f"{tname}.{did}: unknown prototype {pid!r}")
                continue
            if pid in referenced:
                errors.append(f"{tname}.{did}: prototype {pid} shared by definitions")
            referenced.add(pid)
            pb = blocks[pid]
            if pb.get("parent") != did:
                errors.append(f"{tname}.{pid}: prototype parent is not {did}")
            if b.get("topLevel") is not True:
                errors.append(f"{tname}.{did}: definition is not top-level")
            # Argument reporters inside a definition must be declared there.
            declared = set(protos[pid]["names"])
            seen = set()
            stack = [b.get("next")]
            while stack:
                cur = stack.pop()
                if not isinstance(cur, str) or cur in seen or cur not in blocks:
                    continue
                seen.add(cur)
                cb2 = blocks[cur]
                if not isinstance(cb2, dict):
                    continue
                if cb2.get("opcode") in ("procedures_definition",
                                         "procedures_prototype"):
                    continue
                if cb2.get("opcode") in ("argument_reporter_string_number",
                                         "argument_reporter_boolean"):
                    fv = (cb2.get("fields") or {}).get("VALUE")
                    name = fv[0] if isinstance(fv, list) and fv else None
                    if name not in declared and not allow_undeclared_args:
                        errors.append(
                            f"{tname}.{cur}: argument reporter {name!r} is not "
                            f"declared by {protos[pid]['code']!r}")
                nxt = cb2.get("next")
                if isinstance(nxt, str):
                    stack.append(nxt)
                for value in (cb2.get("inputs") or {}).values():
                    if not isinstance(value, list):
                        continue
                    for item in value[1:]:
                        if isinstance(item, str):
                            stack.append(item)
        for pid in protos:
            if pid not in referenced:
                errors.append(f"{tname}.{pid}: prototype has no definition")

        for cid in calls:
            b = blocks[cid]
            mut = b.get("mutation") or {}
            code = mut.get("proccode")
            aids = _parse_json_list(mut.get("argumentids"),
                                    f"{tname}.{cid}.argumentids", errors)
            if not isinstance(code, str):
                errors.append(f"{tname}.{cid}: call has no proccode")
                continue
            matches = [p for p in protos.values() if p["code"] == code]
            if not matches:
                errors.append(f"{tname}.{cid}: unbound call {code!r}")
                continue
            exact = [p for p in matches if p["aids"] == aids]
            if not exact:
                errors.append(
                    f"{tname}.{cid}: argument ids do not match prototype {code!r}")
                continue
            proto = exact[0]
            if len(proto["names"]) != len(aids):
                errors.append(f"{tname}.{cid}: argument count mismatch")
            inputs = b.get("inputs") or {}
            for aid in aids:
                if aid not in inputs:
                    errors.append(f"{tname}.{cid}: missing argument input {aid}")
        for rid in arg_reporters:
            b = blocks[rid]
            fv = (b.get("fields") or {}).get("VALUE")
            name = fv[0] if isinstance(fv, list) and fv else None
            if not isinstance(name, str) or not name:
                errors.append(f"{tname}.{rid}: argument reporter without a name")

        # ---- reachability / cycles ----
        roots = [bid for bid, b in blocks.items()
                 if isinstance(b, dict)
                 and (b.get("topLevel") is True or b.get("parent") is None)]
        seen = set()
        stack = list(roots)
        while stack:
            cur = stack.pop()
            if not isinstance(cur, str) or cur in seen or cur not in blocks:
                continue
            seen.add(cur)
            b = blocks[cur]
            if not isinstance(b, dict):
                continue
            nxt = b.get("next")
            if isinstance(nxt, str):
                stack.append(nxt)
            for value in (b.get("inputs") or {}).values():
                if not isinstance(value, list):
                    continue
                for item in value[1:]:
                    if isinstance(item, str):
                        stack.append(item)
        for bid, b in blocks.items():
            if isinstance(b, dict) and b.get("parent") is not None and bid not in seen:
                errors.append(f"{tname}.{bid}: unreachable block with a parent")

        for bid, b in blocks.items():
            if not isinstance(b, dict):
                continue
            seen_chain = set()
            cur = bid
            while isinstance(cur, str) and cur in blocks:
                if cur in seen_chain:
                    errors.append(f"{tname}.{bid}: cycle in next chain at {cur}")
                    break
                seen_chain.add(cur)
                cb2 = blocks[cur]
                cur = cb2.get("next") if isinstance(cb2, dict) else None

    # ---- monitors / comments ----
    for m in project.get("monitors") or []:
        if not isinstance(m, dict):
            errors.append("monitor is not an object")
            continue
        mid = m.get("id")
        op = m.get("opcode")
        if op == "data_variable" and mid not in var_ids:
            errors.append(f"monitor: unknown variable {mid!r}")
        elif op == "data_listcontents" and mid not in list_ids:
            errors.append(f"monitor: unknown list {mid!r}")
        params = m.get("params") or {}
        if not isinstance(params, dict):
            errors.append("monitor params is not an object")
        else:
            for key in ("VARIABLE", "LIST"):
                if key in params and params[key] not in (
                        var_ids if key == "VARIABLE" else list_ids):
                    errors.append(f"monitor param {key}: unknown id {params[key]!r}")
    for t in targets:
        if not isinstance(t, dict):
            continue
        blocks = t.get("blocks") or {}
        for cid, c in (t.get("comments") or {}).items():
            if not isinstance(c, dict):
                errors.append(f"{t.get('name')}: comment is not an object")
                continue
            anchor = c.get("blockId")
            if anchor is not None and anchor not in blocks:
                errors.append(f"{t.get('name')}.{cid}: dangling comment anchor")
    return errors


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def new_project(blocks, variables=None, lists=None, broadcasts=None,
                name="Stage", is_stage=True):
    return {
        "targets": [{
            "isStage": is_stage, "name": name,
            "variables": variables or {}, "lists": lists or {},
            "broadcasts": broadcasts or {},
            "blocks": blocks, "comments": {},
            "costumes": [], "sounds": [],
        }],
        "monitors": [], "extensions": [], "meta": {"semver": "3.0.0"},
    }


def blk(opcode, **kw):
    b = {"opcode": opcode, "next": None, "parent": None, "inputs": {},
         "fields": {}, "shadow": False, "topLevel": False}
    b.update(kw)
    return b


def run(project, **opts):
    c = Compressor(Options(**opts))
    out = c.run(copy.deepcopy(project))
    return c, out


def check(name, c, out, allow_undeclared_args=False):
    errs = validate_strict(out, allow_undeclared_args=allow_undeclared_args)
    if errs:
        raise AssertionError(f"{name}: structural errors\n" +
                             "\n".join("  " + e for e in errs[:15]))
    return errs


# ---------------------------------------------------------------------------
# Targeted near-duplicate cases
# ---------------------------------------------------------------------------
def build_literal_type_case():
    """Same shape, equal text, different literal shadows (number vs text)."""
    blocks = {}
    hat = "typeHat000000000000"
    blocks[hat] = blk("event_whenflagclicked", topLevel=True, x=0, y=0)
    prev = hat

    def chain(kind, idx, leaf_opcode, literals):
        cur = f"type{kind}Mouse{idx:02d}"
        blocks[cur] = blk(leaf_opcode)
        for j, literal in enumerate(literals):
            aid = f"type{kind}Add{idx:02d}_{j}"
            blocks[aid] = blk("operator_add", inputs={
                "NUM1": [3, cur, [4, ""]], "NUM2": literal})
            blocks[cur]["parent"] = aid
            cur = aid
        return cur

    def add_case(idx, prim):
        nonlocal prev
        gid = f"typeGo{idx:02d}"
        blocks[gid] = blk("motion_gotoxy", parent=prev)
        blocks[prev]["next"] = gid
        prev = gid
        xcur = chain("X", idx, "sensing_mousex", [
            [1, [4, "2"]], [1, [4, "3"]], prim])
        ycur = chain("Y", idx, "sensing_mousey", [
            [1, [4, "4"]], [1, [4, "5"]]])
        blocks[gid]["inputs"] = {"X": [3, xcur, [4, ""]],
                                 "Y": [3, ycur, [4, ""]]}
        blocks[xcur]["parent"] = gid
        blocks[ycur]["parent"] = gid
        return gid

    add_case(0, [1, [4, "1"]])
    add_case(1, [1, [10, "1"]])
    return new_project(blocks)


def build_adjacent_case():
    """Two near-identical large blocks directly adjacent in one stack."""
    blocks = {}
    hat = "adjHat0000000000000"
    blocks[hat] = blk("event_whenflagclicked", topLevel=True, x=0, y=0)
    prev = hat
    for idx in range(2):
        gid = f"adjGo{idx:02d}"
        blocks[gid] = blk("motion_gotoxy", parent=prev)
        blocks[prev]["next"] = gid
        prev = gid
        cur = None
        for j in range(5):
            aid = f"adjAdd{idx:02d}_{j}"
            left = cur if cur else f"adjMouse{idx:02d}"
            # Only the last literal differs, so sharing two large bodies is
            # profitable (the other four literal slots are identical).
            value = str((idx + 1) * 10 + j) if j == 4 else str(10 + j)
            blocks[aid] = blk("operator_add", inputs={
                "NUM1": [3, left, [4, ""]],
                "NUM2": [1, [4, value]],
            })
            if cur is None:
                blocks[f"adjMouse{idx:02d}"] = blk("sensing_mousex", parent=aid)
            else:
                blocks[cur]["parent"] = aid
            cur = aid
        blocks[gid]["inputs"] = {"X": [3, cur, [4, ""]],
                                 "Y": [1, [4, "0"]]}
        blocks[cur]["parent"] = gid
    return new_project(blocks)


def build_substack_case():
    """Near-duplicates inside two if-substacks."""
    blocks = {}
    hat = "subHat0000000000000"
    blocks[hat] = blk("event_whenflagclicked", topLevel=True, x=0, y=0)
    prev = hat
    for idx in range(2):
        cid = f"subIf{idx:02d}"
        blocks[cid] = blk("control_if", parent=prev)
        blocks[prev]["next"] = cid
        prev = cid
        cond = f"subCond{idx:02d}"
        blocks[cond] = blk("operator_equals", parent=cid, inputs={
            "OPERAND1": [1, [4, "1"]], "OPERAND2": [1, [4, "1"]]})
        gid = f"subGo{idx:02d}"
        blocks[gid] = blk("motion_gotoxy", parent=cid)
        blocks[cid]["inputs"] = {"CONDITION": [2, cond],
                                 "SUBSTACK": [2, gid]}
        cur = None
        for j in range(5):
            aid = f"subAdd{idx:02d}_{j}"
            left = cur if cur else f"subMouse{idx:02d}"
            value = str((idx + 1) * 5 + j) if j == 4 else str(5 + j)
            blocks[aid] = blk("operator_add", inputs={
                "NUM1": [3, left, [4, ""]],
                "NUM2": [1, [4, value]],
            })
            if cur is None:
                blocks[f"subMouse{idx:02d}"] = blk("sensing_mousey", parent=aid)
            else:
                blocks[cur]["parent"] = aid
            cur = aid
        blocks[gid]["inputs"] = {"X": [1, [4, "0"]], "Y": [3, cur, [4, ""]]}
        blocks[cur]["parent"] = gid
    return new_project(blocks)


def build_args_near_case(boolean=False):
    """A definition with one argument and two near-duplicate bodies."""
    arena = "ARENA"
    arena_id = "argsArena0000000000"
    blocks = {}
    blocks["argsDef000000000000"] = blk(
        "procedures_definition", topLevel=True, x=0, y=0,
        next="argsBody00000000000", inputs={"custom_block": [1, "argsProto0000000000"]})
    arg_name = "flag" if boolean else "x"
    arg_type = "b" if boolean else "s"
    blocks["argsProto0000000000"] = blk(
        "procedures_prototype", parent="argsDef000000000000", shadow=True,
        inputs={"argid1": [1, [10, ""]]},
        mutation={"tagName": "mutation", "children": [],
                  "proccode": f"argnear %{arg_type}",
                  "argumentids": '["argid1"]',
                  "argumentnames": json.dumps([arg_name]),
                  "argumentdefaults": json.dumps([False if boolean else ""]),
                  "warp": "false"})
    prev = "argsBody00000000000"
    blocks[prev] = blk("data_setvariableto", parent="argsDef000000000000",
                       fields={"VARIABLE": ["ARENA", arena_id]})
    for idx in range(2):
        if boolean:
            gid = f"argsIf{idx:02d}"
            blocks[gid] = blk("control_if", parent=prev)
            blocks[prev]["next"] = gid
            prev = gid
            blocks[f"argsFlag{idx:02d}"] = blk(
                "argument_reporter_boolean", parent=gid,
                fields={"VALUE": [arg_name, None]})
            words = f"argsSay{idx:02d}"
            blocks[words] = blk("looks_say", parent=gid,
                                inputs={"MESSAGE": [1, [10, f"v{idx}"]]})
            # Common tail makes sharing the whole if-block profitable.
            tail = words
            for j in range(8):
                sid = f"argsTail{idx:02d}_{j}"
                # Distinct messages prevent the loop pass from collapsing the
                # common tail before near-duplicate extraction runs.
                blocks[sid] = blk("looks_say", parent=tail,
                                  inputs={"MESSAGE": [1, [10, f"same{j}"]]})
                blocks[tail]["next"] = sid
                tail = sid
            blocks[gid]["inputs"] = {"CONDITION": [2, f"argsFlag{idx:02d}"],
                                     "SUBSTACK": [2, words]}
        else:
            gid = f"argsGo{idx:02d}"
            blocks[gid] = blk("motion_gotoxy", parent=prev)
            blocks[prev]["next"] = gid
            prev = gid
            cur = None
            for j in range(5):
                aid = f"argsAdd{idx:02d}_{j}"
                left = cur if cur else f"argsArg{idx:02d}"
                value = (str((idx + 1) * 7 + j) if j == 4 else str(7 + j))
                blocks[aid] = blk("operator_add", inputs={
                    "NUM1": [3, left, [4, ""]],
                    "NUM2": [1, [4, value]],
                })
                if cur is None:
                    blocks[f"argsArg{idx:02d}"] = blk(
                        "argument_reporter_string_number", parent=aid,
                        fields={"VALUE": [arg_name, None]})
                else:
                    blocks[cur]["parent"] = aid
                cur = aid
            yid = f"argsY{idx:02d}"
            yleaf = f"argsYMouse{idx:02d}"
            blocks[yid] = blk("operator_add", parent=gid, inputs={
                "NUM1": [3, yleaf, [4, ""]], "NUM2": [1, [4, "0"]]})
            blocks[yleaf] = blk("sensing_mousey", parent=yid)
            blocks[gid]["inputs"] = {"X": [3, cur, [4, ""]],
                                     "Y": [3, yid, [4, ""]]}
            blocks[cur]["parent"] = gid
    # One call from a flag script.
    blocks["argsHat000000000000"] = blk("event_whenflagclicked",
                                        topLevel=True, x=0, y=300,
                                        next="argsCall00000000000")
    blocks["argsCall00000000000"] = blk(
        "procedures_call", parent="argsHat000000000000",
        inputs={"argid1": ([2, "argsCallFlag000000"] if boolean
                           else [3, "argsCallVal0000000", [10, ""]])},
        mutation={"tagName": "mutation", "children": [],
                  "proccode": f"argnear %{arg_type}",
                  "argumentids": '["argid1"]', "warp": "false"})
    if boolean:
        blocks["argsCallFlag000000"] = blk(
            "operator_equals", parent="argsCall00000000000",
            inputs={"OPERAND1": [1, [4, "1"]],
                    "OPERAND2": [1, [4, "1"]]})
    else:
        blocks["argsCallVal0000000"] = blk(
            "data_variable", parent="argsCall00000000000",
            fields={"VARIABLE": ["ARENA", arena_id]})
    variables = {arena_id: ["ARENA", 0]}
    return new_project(blocks, variables=variables)


def build_collision_case():
    """Existing ndup1/arg1 names must not be reused."""
    p = build_near_duplicate_sample("literals")
    blocks = p["targets"][0]["blocks"]
    blocks["oldDef0000000000000"] = blk(
        "procedures_definition", topLevel=True, x=0, y=600,
        next="oldStop000000000000", inputs={"custom_block": [1, "oldProto00000000000"]})
    blocks["oldProto00000000000"] = blk(
        "procedures_prototype", parent="oldDef0000000000000", shadow=True,
        mutation={"tagName": "mutation", "children": [],
                  "proccode": "ndup1 %s", "argumentids": '["arg1"]',
                  "argumentnames": '["z"]', "argumentdefaults": '[""]',
                  "warp": "false"})
    blocks["oldStop000000000000"] = blk(
        "looks_say", parent="oldDef0000000000000",
        inputs={"MESSAGE": [1, [10, "old"]]})
    # Keep the existing definition alive (and not inlinable) with two calls.
    blocks["oldHat0000000000000"] = blk(
        "event_whenflagclicked", topLevel=True, x=0, y=900,
        next="oldCall000000000000")
    blocks["oldCall000000000000"] = blk(
        "procedures_call", parent="oldHat0000000000000",
        next="oldCall200000000000",
        inputs={"arg1": [1, [10, "x"]]},
        mutation={"tagName": "mutation", "children": [],
                  "proccode": "ndup1 %s",
                  "argumentids": '["arg1"]', "warp": "false"})
    blocks["oldCall200000000000"] = blk(
        "procedures_call", parent="oldCall000000000000",
        inputs={"arg1": [1, [10, "y"]]},
        mutation={"tagName": "mutation", "children": [],
                  "proccode": "ndup1 %s",
                  "argumentids": '["arg1"]', "warp": "false"})
    return p


def build_warp_near_case():
    """Same near-duplicate pattern inside warp and normal contexts."""
    blocks = {}
    blocks["wnHat000000000000"] = blk("event_whenflagclicked",
                                      topLevel=True, x=0, y=0,
                                      next="wnCall00000000000")
    blocks["wnCall00000000000"] = blk(
        "procedures_call", parent="wnHat000000000000",
        mutation={"tagName": "mutation", "children": [],
                  "proccode": "wnormal", "argumentids": "[]",
                  "warp": "false"})
    blocks["wnDef000000000000"] = blk(
        "procedures_definition", topLevel=True, x=0, y=300,
        next="wnGood1", inputs={"custom_block": [1, "wnProto0000000000"]})
    blocks["wnProto0000000000"] = blk(
        "procedures_prototype", parent="wnDef000000000000", shadow=True,
        mutation={"tagName": "mutation", "children": [],
                  "proccode": "wnormal", "argumentids": "[]",
                  "argumentnames": "[]", "argumentdefaults": "[]",
                  "warp": "false"})
    blocks["wnBody00000000000"] = blk(
        "procedures_definition", topLevel=True, x=300, y=0,
        next="wnWGo1", inputs={"custom_block": [1, "wnWProto000000000"]})
    blocks["wnWProto000000000"] = blk(
        "procedures_prototype", parent="wnBody00000000000", shadow=True,
        mutation={"tagName": "mutation", "children": [],
                  "proccode": "wwarp", "argumentids": "[]",
                  "argumentnames": "[]", "argumentdefaults": "[]",
                  "warp": "true"})
    blocks["wnWCall00000000000"] = blk(
        "procedures_call", parent="wnHat000000000000",
        mutation={"tagName": "mutation", "children": [],
                  "proccode": "wwarp", "argumentids": "[]",
                  "warp": "false"})
    blocks["wnHat000000000000"]["next"] = "wnCall00000000000"
    blocks["wnCall00000000000"]["next"] = "wnWCall00000000000"

    def body(prefix, start, parent, offset):
        blocks[start] = blk("motion_gotoxy", parent=parent)
        cur = None
        for j in range(5):
            aid = f"{prefix}Add{j}"
            left = cur if cur else f"{prefix}Mouse"
            value = str(j + 1 + (offset if j == 4 else 0))
            blocks[aid] = blk("operator_add", inputs={
                "NUM1": [3, left, [4, ""]],
                "NUM2": [1, [4, value]],
            })
            if cur is None:
                blocks[f"{prefix}Mouse"] = blk("sensing_mousex", parent=aid)
            else:
                blocks[cur]["parent"] = aid
            cur = aid
        blocks[start]["inputs"] = {"X": [3, cur, [4, ""]], "Y": [1, [4, "0"]]}
        blocks[cur]["parent"] = start
        return start

    # two near-identical copies in the normal definition
    body("wnA", "wnGood1", "wnDef000000000000", 0)
    body("wnB", "wnGood2", "wnGood1", 100)
    # two near-identical copies in the warp definition
    body("wnC", "wnWGo1", "wnBody00000000000", 0)
    body("wnD", "wnWGo2", "wnWGo1", 100)
    blocks["wnGood1"]["next"] = "wnGood2"
    blocks["wnWGo1"]["next"] = "wnWGo2"
    return new_project(blocks)


# ---------------------------------------------------------------------------
# Fuzz generator
# ---------------------------------------------------------------------------
class ProjectGen:
    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.n = 0
        self.blocks = {}
        self.defs = []
        self.stage_vars = {"gA": ["gA", 0], "gB": ["gB", 1],
                           "gC": ["gC", 2], "sA": ["sA", 0], "sB": ["sB", 1]}
        self.stage_lists = {"gL": ["gL", ["x", "y"]]}
        self.broadcasts = {"gBc": ["msg", 0]}
        # This generator emits one Stage target, so all variables are global.
        self.local_vars = {}

    def nid(self, prefix="b"):
        self.n += 1
        return f"{prefix}{self.n:05d}"

    def add(self, opcode, **kw):
        bid = self.nid("b")
        self.blocks[bid] = blk(opcode, **kw)
        return bid

    def num(self):
        return str(self.rng.choice([-5, -1, 0, 1, 2, 3, 7, 10, 0.5, -2.5,
                                    42, 100]))

    def text(self):
        return self.rng.choice(["hi", "a", "", "text", "%s", "0", "1", "x y"])

    def literal(self):
        if self.rng.random() < 0.5:
            return [4, self.num()]
        return [10, self.text()]

    def value_reporter(self, depth=0):
        """Return an input entry or None that can fill a value slot."""
        if depth >= 3 or self.rng.random() < 0.45:
            return [1, self.literal()], None
        op = self.rng.choice([
            "operator_add", "operator_subtract", "operator_multiply",
            "operator_divide", "operator_mod", "operator_random",
            "operator_round", "operator_mathop", "operator_join",
            "operator_letter_of", "operator_length", "sensing_mousex",
            "sensing_mousey", "sensing_timer", "data_variable",
            "data_itemoflist", "data_lengthoflist",
        ])
        bid = self.nid("r")
        b = blk(op, parent=None)
        self.blocks[bid] = b
        if op in ("operator_add", "operator_subtract", "operator_multiply",
                  "operator_divide", "operator_mod"):
            for key in ("NUM1", "NUM2"):
                entry, child = self.value_reporter(depth + 1)
                b["inputs"][key] = entry
                if child:
                    self.blocks[child]["parent"] = bid
        elif op == "operator_random":
            for key in ("FROM", "TO"):
                entry, child = self.value_reporter(depth + 1)
                b["inputs"][key] = entry
                if child:
                    self.blocks[child]["parent"] = bid
        elif op == "operator_round":
            entry, child = self.value_reporter(depth + 1)
            b["inputs"]["NUM"] = entry
            if child:
                self.blocks[child]["parent"] = bid
        elif op == "operator_mathop":
            entry, child = self.value_reporter(depth + 1)
            b["inputs"]["NUM"] = entry
            if child:
                self.blocks[child]["parent"] = bid
            b["fields"]["OPERATOR"] = [
                self.rng.choice(["abs", "floor", "ceiling", "sqrt", "sin",
                                 "cos", "tan", "ln", "log", "e ^", "10 ^"]),
                None]
        elif op == "operator_join":
            for key in ("STRING1", "STRING2"):
                entry, child = self.value_reporter(depth + 1)
                b["inputs"][key] = entry
                if child:
                    self.blocks[child]["parent"] = bid
        elif op == "operator_letter_of":
            entry, child = self.value_reporter(depth + 1)
            b["inputs"]["LETTER"] = entry
            if child:
                self.blocks[child]["parent"] = bid
            entry, child = self.value_reporter(depth + 1)
            b["inputs"]["STRING"] = entry
            if child:
                self.blocks[child]["parent"] = bid
        elif op == "operator_length":
            entry, child = self.value_reporter(depth + 1)
            b["inputs"]["STRING"] = entry
            if child:
                self.blocks[child]["parent"] = bid
        elif op == "data_variable":
            name = self.rng.choice(list(self.stage_vars) + list(self.local_vars))
            table = self.stage_vars if name in self.stage_vars else self.local_vars
            b["fields"]["VARIABLE"] = [name, name]
        elif op == "data_itemoflist":
            b["fields"]["LIST"] = ["gL", "gL"]
            entry, child = self.value_reporter(depth + 1)
            b["inputs"]["INDEX"] = entry
            if child:
                self.blocks[child]["parent"] = bid
        elif op == "data_lengthoflist":
            b["fields"]["LIST"] = ["gL", "gL"]
        return [3, bid, [10, ""]], bid

    def bool_reporter(self, depth=0):
        if depth >= 3:
            entry, child = self.value_reporter(depth + 1)
            return [2, child] if child else [1, [10, ""]], child
        op = self.rng.choice(["operator_equals", "operator_lt",
                              "operator_gt", "operator_and", "operator_or",
                              "operator_not", "operator_contains"])
        bid = self.nid("r")
        b = blk(op, parent=None)
        self.blocks[bid] = b
        if op in ("operator_equals", "operator_lt", "operator_gt"):
            for key in ("OPERAND1", "OPERAND2"):
                entry, child = self.value_reporter(depth + 1)
                b["inputs"][key] = entry
                if child:
                    self.blocks[child]["parent"] = bid
        elif op in ("operator_and", "operator_or"):
            for key in ("OPERAND1", "OPERAND2"):
                entry, child = self.bool_reporter(depth + 1)
                b["inputs"][key] = entry
                if child:
                    self.blocks[child]["parent"] = bid
        elif op == "operator_not":
            entry, child = self.bool_reporter(depth + 1)
            b["inputs"]["OPERAND"] = entry
            if child:
                self.blocks[child]["parent"] = bid
        else:
            entry, child = self.value_reporter(depth + 1)
            b["inputs"]["STRING1"] = entry
            if child:
                self.blocks[child]["parent"] = bid
            entry, child = self.value_reporter(depth + 1)
            b["inputs"]["STRING2"] = entry
            if child:
                self.blocks[child]["parent"] = bid
        return [2, bid], bid

    def stack_chain(self, parent, depth=0, length=None):
        prev = parent
        for _ in range(length or self.rng.randint(2, 6)):
            choice = self.rng.random()
            if choice < 0.18 and depth < 2:
                kind = self.rng.choice(["control_if", "control_if_else",
                                        "control_repeat"])
                bid = self.add(kind, parent=prev)
                self.blocks[prev]["next"] = bid
                entry, child = self.bool_reporter()
                self.blocks[bid]["inputs"]["CONDITION"] = entry
                if child:
                    self.blocks[child]["parent"] = bid
                if kind == "control_repeat":
                    entry, child = self.value_reporter()
                    self.blocks[bid]["inputs"]["TIMES"] = entry
                    if child:
                        self.blocks[child]["parent"] = bid
                sub = self.nid("b")
                self.blocks[sub] = blk("looks_say", parent=bid,
                                       inputs={"MESSAGE": [1, [10, "sub"]]})
                self.blocks[bid]["inputs"]["SUBSTACK"] = [2, sub]
                self.stack_chain(sub, depth + 1)
                prev = bid
            elif choice < 0.30 and self.defs:
                code, call_args = self.rng.choice(self.defs)
                bid = self.add("procedures_call", parent=prev)
                self.blocks[prev]["next"] = bid
                aids = []
                for aid, (argname, is_bool) in call_args:
                    aids.append(aid)
                    if is_bool:
                        entry, child = self.bool_reporter()
                        self.blocks[bid]["inputs"][aid] = entry
                    else:
                        entry, child = self.value_reporter()
                        self.blocks[bid]["inputs"][aid] = entry
                    if child:
                        self.blocks[child]["parent"] = bid
                self.blocks[bid]["mutation"] = {
                    "tagName": "mutation", "children": [],
                    "proccode": code,
                    "argumentids": json.dumps(aids, separators=(",", ":")),
                    "warp": "false"}
                prev = bid
            else:
                op = self.rng.choice([
                    "motion_movesteps", "motion_turnright",
                    "motion_gotoxy", "looks_say", "looks_think",
                    "looks_seteffectto", "control_wait", "data_setvariableto",
                    "data_changevariableby", "event_broadcast", "pen_penDown",
                    "pen_penUp", "pen_clear",
                ])
                bid = self.add(op, parent=prev)
                self.blocks[prev]["next"] = bid
                if op == "motion_movesteps":
                    e, c = self.value_reporter()
                    self.blocks[bid]["inputs"]["STEPS"] = e
                    if c:
                        self.blocks[c]["parent"] = bid
                elif op == "motion_turnright":
                    e, c = self.value_reporter()
                    self.blocks[bid]["inputs"]["DEGREES"] = e
                    if c:
                        self.blocks[c]["parent"] = bid
                elif op == "motion_gotoxy":
                    for key in ("X", "Y"):
                        e, c = self.value_reporter()
                        self.blocks[bid]["inputs"][key] = e
                        if c:
                            self.blocks[c]["parent"] = bid
                elif op in ("looks_say", "looks_think"):
                    e, c = self.value_reporter()
                    self.blocks[bid]["inputs"]["MESSAGE"] = e
                    if c:
                        self.blocks[c]["parent"] = bid
                elif op == "looks_seteffectto":
                    self.blocks[bid]["fields"]["EFFECT"] = [
                        self.rng.choice(["ghost", "color", "brightness"]), None]
                    e, c = self.value_reporter()
                    self.blocks[bid]["inputs"]["VALUE"] = e
                    if c:
                        self.blocks[c]["parent"] = bid
                elif op == "control_wait":
                    e, c = self.value_reporter()
                    self.blocks[bid]["inputs"]["DURATION"] = e
                    if c:
                        self.blocks[c]["parent"] = bid
                elif op in ("data_setvariableto", "data_changevariableby"):
                    name = self.rng.choice(list(self.stage_vars) + list(self.local_vars))
                    self.blocks[bid]["fields"]["VARIABLE"] = [name, name]
                    key = "VALUE" if op == "data_setvariableto" else "VALUE"
                    e, c = self.value_reporter()
                    self.blocks[bid]["inputs"][key] = e
                    if c:
                        self.blocks[c]["parent"] = bid
                elif op == "event_broadcast":
                    self.blocks[bid]["fields"]["BROADCAST_OPTION"] = ["msg", "gBc"]
                prev = bid
        return prev

    def add_definition(self):
        code = f"proc{len(self.defs) + 1}"
        args = []
        for i in range(self.rng.randint(0, 2)):
            args.append((f"a{i}", self.rng.random() < 0.3))
        aids = [f"d{len(self.defs)}_{i}" for i in range(len(args))]
        placeholders = " ".join("%b" if b else "%s" for _, b in args)
        full_code = code + (f" {placeholders}" if placeholders else "")
        defid = self.nid("b")
        protid = self.nid("b")
        self.blocks[defid] = blk(
            "procedures_definition", topLevel=True, x=0,
            y=100 + len(self.defs) * 100,
            inputs={"custom_block": [1, protid]})
        self.blocks[protid] = blk(
            "procedures_prototype", parent=defid, shadow=True,
            mutation={"tagName": "mutation", "children": [],
                      "proccode": full_code,
                      "argumentids": json.dumps(aids, separators=(",", ":")),
                      "argumentnames": json.dumps([n for n, _ in args]),
                      "argumentdefaults": json.dumps(
                          [False if b else "" for _, b in args]),
                      "warp": "true" if self.rng.random() < 0.2 else "false"})
        body = self.nid("b")
        self.blocks[body] = blk("looks_say", parent=defid,
                                inputs={"MESSAGE": [1, [10, code]]})
        self.blocks[defid]["next"] = body
        self.stack_chain(body, 1)
        self.defs.append((full_code, list(zip(aids, args))))

    def add_near_template(self):
        for idx in range(3):
            self.add_near_gotoxy(idx)

    def add_near_gotoxy(self, idx):
        hat = self.nid("b")
        self.blocks[hat] = blk("event_whenflagclicked", topLevel=True,
                               x=idx * 400, y=800)
        gid = self.nid("b")
        self.blocks[gid] = blk("motion_gotoxy", parent=hat)
        self.blocks[hat]["next"] = gid
        cur = None
        for j in range(5):
            aid = self.nid("r")
            left = cur if cur else self.nid("r")
            self.blocks[aid] = blk("operator_add", inputs={
                "NUM1": [3, left, [4, ""]],
                "NUM2": [1, [4, str((idx + 1) * 100 + j)]],
            })
            if cur is None:
                self.blocks[left] = blk("sensing_mousex", parent=aid)
            else:
                self.blocks[cur]["parent"] = aid
            cur = aid
        self.blocks[gid]["inputs"] = {"X": [3, cur, [4, ""]],
                                      "Y": [1, [4, str(idx * 3)]]}
        self.blocks[cur]["parent"] = gid

    def build(self):
        for _ in range(self.rng.randint(1, 3)):
            self.add_definition()
        for i in range(self.rng.randint(2, 4)):
            hat = self.nid("b")
            self.blocks[hat] = blk("event_whenflagclicked", topLevel=True,
                                   x=i * 400, y=0)
            self.stack_chain(hat, 0)
        self.add_near_template()
        targets = [{
            "isStage": True, "name": "Stage",
            "variables": self.stage_vars, "lists": self.stage_lists,
            "broadcasts": self.broadcasts,
            "blocks": self.blocks, "comments": {},
            "costumes": [], "sounds": [],
        }]
        return {"targets": targets, "monitors": [], "extensions": [],
                "meta": {"semver": "3.0.0"}}


# ---------------------------------------------------------------------------
# Test runners
# ---------------------------------------------------------------------------
def test_targeted():
    print("[strict] targeted near-duplicate cases...")

    # literal-only merge (keep generated proccodes so they can be inspected)
    c, out = run(build_near_duplicate_sample("literals"), compress_procs=False)
    check("literal-only", c, out)
    assert c.stats["near_duplicates_extracted"] == 1, c.stats
    assert c.stats["near_blocks_saved"] >= 10, c.stats
    protos = [b for b in out["targets"][0]["blocks"].values()
              if isinstance(b, dict) and b.get("opcode") == "procedures_prototype"]
    near = [p for p in protos if (p.get("mutation") or {}).get("proccode", "").startswith("ndup")]
    assert len(near) == 1, [p["mutation"]["proccode"] for p in near]
    assert len(json.loads(near[0]["mutation"]["argumentnames"])) == 2

    # field differences must block merging
    c, out = run(build_near_duplicate_sample("field"))
    check("field-difference", c, out)
    assert c.stats["near_duplicates_extracted"] == 0, c.stats
    assert not any(isinstance(b, dict) and b.get("opcode") == "procedures_definition"
                   for b in out["targets"][0]["blocks"].values())

    # number vs text literal in the same slot
    c, out = run(build_literal_type_case())
    check("literal-type", c, out)
    assert c.stats["near_duplicates_extracted"] == 1, c.stats
    calls = [b for b in out["targets"][0]["blocks"].values()
             if isinstance(b, dict) and b.get("opcode") == "procedures_call"]
    assert calls, "no near-duplicate call"
    seen = []
    for call in calls:
        for aid in json.loads(call["mutation"]["argumentids"]):
            ref = call["inputs"][aid]
            assert ref[0] == 1 and isinstance(ref[1], list), ref
            seen.append(tuple(ref[1]))
    assert ([4, "1"] in [list(x) for x in seen]
            and [10, "1"] in [list(x) for x in seen]), seen

    # adjacent occurrences
    c, out = run(build_adjacent_case())
    check("adjacent", c, out)
    assert c.stats["near_duplicates_extracted"] >= 1, c.stats

    # occurrences inside two substacks
    c, out = run(build_substack_case())
    check("substack", c, out)
    assert c.stats["near_duplicates_extracted"] >= 1, c.stats

    # existing definition argument + literal arguments.  Disable the earlier
    # exact/loop passes so the near pass sees the full common body.
    c, out = run(build_args_near_case(False), extract_duplicates=False,
                 loop_duplicates=False)
    check("args+literal", c, out)
    assert c.stats["near_duplicates_extracted"] >= 1, c.stats
    assert c.stats["near_blocks_saved"] >= 1
    # every call must have both an argument reporter and a literal argument
    blocks = out["targets"][0]["blocks"]
    calls = [b for b in blocks.values()
             if isinstance(b, dict) and b.get("opcode") == "procedures_call"]
    literal_calls = 0
    for call in calls:
        for aid in json.loads(call["mutation"]["argumentids"]):
            ref = call["inputs"][aid]
            if ref[0] == 1 and isinstance(ref[1], list):
                literal_calls += 1
    assert literal_calls >= 2, literal_calls

    # boolean argument + literal argument
    c, out = run(build_args_near_case(True), extract_duplicates=False,
                 loop_duplicates=False)
    check("bool-args+literal", c, out)
    assert c.stats["near_duplicates_extracted"] >= 1, c.stats

    # proccode/argument-id collision avoidance
    c, out = run(build_collision_case(), compress_procs=False)
    check("collision", c, out)
    codes = [b["mutation"]["proccode"] for b in out["targets"][0]["blocks"].values()
             if isinstance(b, dict) and b.get("opcode") == "procedures_prototype"]
    assert "ndup1 %s" in codes, codes
    assert any(code.startswith("ndup2") for code in codes), codes
    assert c.stats["near_duplicates_extracted"] == 1, c.stats

    # warp and normal contexts must not be mixed
    c, out = run(build_warp_near_case(), compress_procs=False)
    check("warp-context", c, out)
    blocks = out["targets"][0]["blocks"]
    protos = {b["mutation"]["proccode"]: b for b in blocks.values()
              if isinstance(b, dict) and b.get("opcode") == "procedures_prototype"}
    generated = {code: p for code, p in protos.items()
                 if code.startswith("ndup")}
    assert generated, list(protos)
    warp_flags = {p["mutation"].get("warp") for p in generated.values()}
    assert warp_flags == {"true", "false"}, warp_flags

    # tiny near-duplicates must not grow the project
    p = build_near_duplicate_sample("literals")
    # Replace the big bodies with two tiny say blocks that differ only in text.
    tiny = new_project({
        "tinyHat000000000000": blk("event_whenflagclicked", topLevel=True,
                                   x=0, y=0, next="tinySay00000000000"),
        "tinySay00000000000": blk("looks_say", parent="tinyHat000000000000",
                                  inputs={"MESSAGE": [1, [10, "a"]]},
                                  next="tinySay20000000000"),
        "tinySay20000000000": blk("looks_say", parent="tinySay00000000000",
                                  inputs={"MESSAGE": [1, [10, "b"]]}),
    })
    c, out = run(tiny)
    check("tiny-profitability", c, out)
    assert c.stats["near_duplicates_extracted"] == 0, c.stats
    assert not any(isinstance(b, dict) and b.get("opcode") == "procedures_definition"
                   for b in out["targets"][0]["blocks"].values())

    # near-extraction can be disabled
    c, out = run(build_near_duplicate_sample("literals"), near_duplicates=False)
    check("disabled", c, out)
    assert c.stats["near_duplicates_extracted"] == 0
    assert not any(isinstance(b, dict) and b.get("opcode") == "procedures_definition"
                   for b in out["targets"][0]["blocks"].values())
    print("[strict] targeted near-duplicate cases OK")


def test_determinism_and_real():
    print("[strict] determinism and real projects...")
    base = os.path.dirname(os.path.abspath(__file__))
    for fname in ("test.sb3", "repeat.sb3"):
        path = os.path.join(base, fname)
        if not os.path.isfile(path):
            print(f"[strict] skip missing {fname}")
            continue
        project, _, _, _ = load_input(path)
        c1, out1 = run(project)
        check(fname, c1, out1, allow_undeclared_args=True)
        c2, out2 = run(project)
        check(fname + " (again)", c2, out2, allow_undeclared_args=True)
        s1 = json.dumps(out1, ensure_ascii=False, separators=(",", ":"))
        s2 = json.dumps(out2, ensure_ascii=False, separators=(",", ":"))
        assert s1 == s2, f"{fname}: non-deterministic output"
        c3, off = run(project, near_duplicates=False)
        check(fname + " near-off", c3, off, allow_undeclared_args=True)
        assert c3.stats["near_duplicates_extracted"] == 0
        on_blocks = sum(len(t.get("blocks") or {}) for t in out1["targets"])
        off_blocks = sum(len(t.get("blocks") or {}) for t in off["targets"])
        on_json = len(s1)
        off_json = len(json.dumps(off, ensure_ascii=False, separators=(",", ":")))
        assert on_blocks <= off_blocks, (fname, on_blocks, off_blocks)
        assert on_json <= off_json, (fname, on_json, off_json)
        assert c1.stats["near_duplicates_extracted"] >= 0
        print(f"[strict] {fname}: blocks {off_blocks}->{on_blocks}, "
              f"json {off_json}->{on_json}, near groups "
              f"{c1.stats['near_duplicates_extracted']}")

    # The real-world 背景 example: 1st/3rd merge with four literal args.
    path = os.path.join(base, "test.sb3")
    if os.path.isfile(path):
        project, _, _, _ = load_input(path)
        c, out = run(project, compress_procs=False)
        check("背景", c, out, allow_undeclared_args=True)
        codes = {}
        all_blocks = []
        for tgt in out["targets"]:
            target_blocks = tgt.get("blocks") or {}
            all_blocks.extend(target_blocks.values())
            for b in target_blocks.values():
                if isinstance(b, dict) and b.get("opcode") == "procedures_prototype":
                    codes[(b.get("mutation") or {}).get("proccode")] = b
        assert "ndup1 %s %s %s %s" in codes, list(codes)
        calls = [b for b in all_blocks
                 if isinstance(b, dict) and b.get("opcode") == "procedures_call"
                 and (b.get("mutation") or {}).get("proccode")
                 == "ndup1 %s %s %s %s"]
        assert len(calls) == 2, len(calls)
        values = set()
        for call in calls:
            vals = []
            for aid in json.loads(call["mutation"]["argumentids"]):
                ref = call["inputs"][aid]
                assert ref[0] == 1 and isinstance(ref[1], list), ref
                vals.append(tuple(ref[1]))
            values.add(tuple(vals))
        assert values == {((4, "35"), (4, "8"), (4, "69"), (4, "8")),
                          ((4, "33"), (4, "4"), (4, "15"), (4, "4"))}, values
        print("[strict] 背景 gotoxy pair: 4 literal arguments OK")


def test_fuzz(count=200):
    print(f"[strict] fuzzing {count} seeded projects...")
    for seed in range(count):
        p = ProjectGen(seed).build()
        input_errors = validate_strict(p)
        if input_errors:
            raise AssertionError(
                f"seed {seed}: generator produced an invalid project\n" +
                "\n".join("  " + e for e in input_errors[:10]))
        c, out = run(p)
        check(f"seed {seed}", c, out)
        c2, out2 = run(p)
        s1 = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
        s2 = json.dumps(out2, ensure_ascii=False, separators=(",", ":"))
        assert s1 == s2, f"seed {seed}: non-deterministic output"
        c_off, out_off = run(p, near_duplicates=False)
        check(f"seed {seed} near-off", c_off, out_off)
        assert c_off.stats["near_duplicates_extracted"] == 0
        on_blocks = sum(len(t.get("blocks") or {}) for t in out["targets"])
        in_blocks = sum(len(t.get("blocks") or {}) for t in p["targets"])
        assert on_blocks <= in_blocks, (seed, in_blocks, on_blocks)
        off_blocks = sum(len(t.get("blocks") or {}) for t in out_off["targets"])
        assert on_blocks <= off_blocks, (seed, on_blocks, off_blocks)
        on_json = len(s1)
        in_json = len(json.dumps(p, ensure_ascii=False, separators=(",", ":")))
        assert on_json <= in_json, (seed, in_json, on_json)
        off_json = len(json.dumps(out_off, ensure_ascii=False,
                                  separators=(",", ":")))
        assert on_json <= off_json, (seed, on_json, off_json)
        if seed and seed % 50 == 0:
            print(f"[strict]   ... seed {seed} OK")
    print("[strict] fuzz OK")


def main():
    test_targeted()
    test_determinism_and_real()
    test_fuzz()
    print("\nSTRICT TESTS PASSED")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""sb3_compressor.py の検証テスト。"""
import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sb3_compressor import Options, Compressor, compress_file, default_output_path

VID_SCORE = "gV0001aaaabbbbccccdddd"
VID_CLOUD = "gV0002aaaabbbbccccdddd"
LID_MYLIST = "gL0001aaaabbbbccccdddd"
BID_GO = "bB0001aaaabbbbccccdddd"
BID_MSG2 = "bB0002aaaabbbbccccdddd"
LID_LOCAL = "sV0001aaaabbbbccccdddd"


def build_sample():
    def blk(opcode, **kw):
        b = {"opcode": opcode, "next": None, "parent": None, "inputs": {},
             "fields": {}, "shadow": False, "topLevel": False}
        b.update(kw)
        return b

    stage_blocks = {
        "blk00000000000000000001": blk("event_whenflagclicked", topLevel=True,
                                       x=0, y=0, next="blk00000000000000000002"),
        "blk00000000000000000002": blk("data_setvariableto",
                                       next="blk00000000000000000003",
                                       parent="blk00000000000000000001",
                                       inputs={"VALUE": [1, [10, "10"]]},
                                       fields={"VARIABLE": ["score", VID_SCORE]}),
        "blk00000000000000000003": blk("event_broadcast",
                                       next="blk00000000000000000004",
                                       parent="blk00000000000000000002",
                                       inputs={"BROADCAST_INPUT": [1, [11, "go!", BID_GO]]}),
        "blk00000000000000000004": blk("data_setvariableto",
                                       parent="blk00000000000000000003",
                                       inputs={"VALUE": [1, [10, "0"]]},
                                       fields={"VARIABLE":
                                               ["\u2601 cloudvar", VID_CLOUD]}),
    }
    sprite_blocks = {
        "sp0000000000000000001": blk("event_whenflagclicked", topLevel=True,
                                     x=5, y=5, next="sp0000000000000000002"),
        "sp0000000000000000002": blk("control_repeat",
                                     next="sp0000000000000000009",
                                     parent="sp0000000000000000001",
                                     inputs={"TIMES": [1, [6, "3"]],
                                             "SUBSTACK": [2, "sp0000000000000000003"]}),
        "sp0000000000000000003": blk("motion_movesteps",
                                     next="sp0000000000000000004",
                                     parent="sp0000000000000000002",
                                     inputs={"STEPS": [1, [4, "10"]]}),
        "sp0000000000000000004": blk("looks_say",
                                     parent="sp0000000000000000003",
                                     inputs={"MESSAGE": [3, "sp0000000000000000006",
                                                         [10, ""]]}),
        "sp0000000000000000006": blk("data_variable",
                                     parent="sp0000000000000000004",
                                     fields={"VARIABLE": ["score", VID_SCORE]}),
        "sp0000000000000000007": blk("event_whenthisspriteclicked", topLevel=True,
                                     x=-100, y=100),
        "sp0000000000000000008": blk("procedures_definition", topLevel=True, x=20, y=20,
                                     next="sp000000000000000000a",
                                     inputs={"custom_block": [1, "PROTOSAMPLE0000000"]}),
        "PROTOSAMPLE0000000": blk("procedures_prototype",
                                  parent="sp0000000000000000008",
                                  inputs={"ARG1": [1, [10, "arg"]]},
                                  mutation={"proccode": "do %s", "warp": True,
                                            "argumentids": "[\"ARG1\"]",
                                            "argumentnames": "[\"\u540d\"]"}),
        "sp0000000000000000009": blk("procedures_call",
                                     parent="sp0000000000000000002",
                                     mutation={"proccode": "do %s"},
                                     inputs={"ARG1": [1, [10, "x"]]}),
        "sp000000000000000000a": blk("data_setvariableto",
                                     parent="sp0000000000000000008",
                                     inputs={"VALUE": [3, "sp000000000000000000b",
                                                       [10, ""]]},
                                     fields={"VARIABLE": ["local", LID_LOCAL]}),
        "sp000000000000000000b": blk("operator_add",
                                     parent="sp000000000000000000a",
                                     inputs={"OPERAND1": [3, "sp000000000000000000c",
                                                          [4, "0"]],
                                             "OPERAND2": [3, "sp000000000000000000d",
                                                          [4, "0"]]}),
        "sp000000000000000000c": blk("data_variable",
                                     parent="sp000000000000000000b",
                                     fields={"VARIABLE": ["score", VID_SCORE]}),
        "sp000000000000000000d": blk("argument_reporter_string_number",
                                     parent="sp000000000000000000b",
                                     fields={"VALUE": ["\u540d", None]}),
        "strayreporter000000000": blk("argument_reporter_string_number",
                                      topLevel=True, x=-150, y=-80,
                                      fields={"VALUE": ["\u540d", None]}),
    }
    project = {
        "targets": [
            {"isStage": True, "name": "Stage",
             "variables": {VID_SCORE: ["score", 0], VID_CLOUD: ["\u2601 cloudvar", 0]},
             "lists": {LID_MYLIST: ["mylist", ["a", "b"]]},
             "broadcasts": {BID_GO: "go!", BID_MSG2: ["msg2"]},
             "blocks": stage_blocks, "comments": {},
             "costumes": [{"name": "backdrop1", "dataFormat": "svg",
                           "assetId": "cd21514d0531fdffb22204e0ec5ed84a",
                           "md5ext": "cd21514d0531fdffb22204e0ec5ed84a.svg",
                           "rotationCenterX": 240, "rotationCenterY": 180}],
             "currentCostume": 0, "volume": 100, "tempo": 60,
             "videoTransparency": 50, "videoState": "on",
             "textToSpeechLanguage": None, "layerOrder": 0},
            {"isStage": False, "name": "Sprite1",
             "variables": {LID_LOCAL: ["local", 0]},
             "lists": {}, "broadcasts": {},
             "blocks": sprite_blocks,
             "comments": {"cmt0001aaaaaaaaaaaaaaaa": {
                 "blockId": "sp0000000000000000002", "x": 0, "y": 0,
                 "width": 200, "height": 200, "minimized": False, "text": "note"}},
             "costumes": [{"name": "costume1", "dataFormat": "svg",
                           "assetId": "bcf454acf82e4504149f7ffe07081dbc",
                           "bitmapResolution": 1,
                           "md5ext": "bcf454acf82e4504149f7ffe07081dbc.svg",
                           "rotationCenterX": 0, "rotationCenterY": 0}],
             "sounds": [{"name": "pop", "assetId": "83a9787ae4b0ceac7b70e0e251debc0b",
                         "dataFormat": "wav", "format": "", "rate": 11025,
                         "sampleCount": 258,
                         "md5ext": "83a9787ae4b0ceac7b70e0e251debc0b.wav"}],
             "volume": 100, "layerOrder": 1,
             "visible": True, "x": 0, "y": 0, "size": 100, "direction": 90,
             "draggable": False, "rotationStyle": "all around"},
        ],
        "monitors": [
            {"id": VID_SCORE, "mode": "default", "opcode": "data_variable",
             "params": {"VARIABLE": "score"}, "spriteName": None, "value": 0,
             "width": 0, "height": 0, "x": 5, "y": 5, "visible": True,
             "sliderMin": 0, "sliderMax": 100, "isDiscrete": True},
            {"id": LID_MYLIST, "mode": "list", "opcode": "data_listcontents",
             "params": {"LIST": "mylist"}, "spriteName": None, "value": [],
             "width": 0, "height": 0, "x": 155, "y": 5, "visible": False},
            {"id": "timerMon00000000000000", "mode": "default",
             "opcode": "sensing_timer", "params": {}, "spriteName": None,
             "value": 0, "width": 0, "height": 0, "x": 5, "y": 200, "visible": True},
        ],
        "extensions": [],
        "meta": {"semver": "3.0.0", "vm": "0.2.0", "agent": "",
                 "platform": {"name": "TurboWarp", "url": "https://turbowarp.org/"}},
    }
    return project


def validate_project(project):
    errs = []
    var_ids, list_ids, bc_ids, bc_names = set(), set(), set(), set()
    bc_name_by_id = {}
    for t in project.get("targets", []):
        var_ids |= set((t.get("variables") or {}).keys())
        list_ids |= set((t.get("lists") or {}).keys())
        bc = t.get("broadcasts") or {}
        bc_ids |= set(bc.keys())
        for bid_key, ent in bc.items():
            nm = ent[0] if isinstance(ent, list) else ent
            bc_names.add(nm)
            bc_name_by_id[bid_key] = nm

    def find_name(table_by_id, table_ent_index, wanted_id):
        for tid, ent in table_by_id.items():
            if tid == wanted_id:
                return ent[table_ent_index]
        return None

    for t in project.get("targets", []):
        blocks = t.get("blocks") or {}
        for bid, b in blocks.items():
            if isinstance(b, list):
                if b and b[0] in (12, 13):
                    tab = var_ids if b[0] == 12 else list_ids
                    pid = b[2] if len(b) > 2 else None
                    if pid not in tab:
                        errs.append(f"{bid}: 単独レポーターの変数/リストIDが存在しない ({pid})")
                continue
            if not isinstance(b, dict):
                continue
            nxt = b.get("next")
            if nxt is not None and nxt not in blocks:
                errs.append(f"{bid}: next が不正 ({nxt})")
            par = b.get("parent")
            if par is not None and par not in blocks:
                errs.append(f"{bid}: parent が不正 ({par})")
            for k, v in (b.get("inputs") or {}).items():
                if not isinstance(v, list):
                    errs.append(f"{bid}.{k}: inputs の形式が不正")
                    continue
                for item in v[1:]:
                    if isinstance(item, str):
                        if item not in blocks:
                            errs.append(f"{bid}.{k}: ブロック参照が存在しない ({item})")
                    elif isinstance(item, list) and item:
                        if item[0] in (12, 13):
                            tab = var_ids if item[0] == 12 else list_ids
                            pid = item[2] if len(item) > 2 else None
                            if pid not in tab:
                                errs.append(f"{bid}.{k}: 変数/リストIDが存在しない ({pid})")
                        elif item[0] == 11:
                            if len(item) > 1 and item[1] not in bc_names:
                                errs.append(f"{bid}.{k}: 放送名が存在しない ({item[1]})")
                            if len(item) > 2:
                                if item[2] not in bc_ids:
                                    errs.append(f"{bid}.{k}: 放送IDが存在しない ({item[2]})")
                                elif bc_name_by_id.get(item[2]) != item[1]:
                                    errs.append(f"{bid}.{k}: 放送名とIDの不一致 "
                                                f"({item[1]} vs {item[2]})")
            for k, fv in (b.get("fields") or {}).items():
                if not isinstance(fv, list) or not fv:
                    continue
                fid = fv[1] if len(fv) > 1 else None
                if k == "VARIABLE" and fid and fid not in var_ids:
                    errs.append(f"{bid}.{k}: 変数IDが存在しない ({fid})")
                elif k == "LIST" and fid and fid not in list_ids:
                    errs.append(f"{bid}.{k}: リストIDが存在しない ({fid})")
                elif k == "BROADCAST_OPTION" and fid and fid not in bc_ids:
                    errs.append(f"{bid}.{k}: 放送IDが存在しない ({fid})")

    for m in project.get("monitors", []) or []:
        op = m.get("opcode")
        mid = m.get("id")
        if op == "data_variable" and mid not in var_ids:
            errs.append(f"monitor(data_variable): IDが存在しない ({mid})")
        elif op == "data_listcontents" and mid not in list_ids:
            errs.append(f"monitor(data_listcontents): IDが存在しない ({mid})")

    # 手続き: 呼び出しは必ずいずれかの定義に束縛される / mutation整合性
    for t in project.get("targets", []):
        blocks = t.get("blocks") or {}
        def_codes = set()
        calls = []
        for b in blocks.values():
            if not isinstance(b, dict):
                continue
            op = b.get("opcode")
            if op == "procedures_definition":
                cb = (b.get("inputs") or {}).get("custom_block")
                pid = cb[1] if isinstance(cb, list) and len(cb) > 1 else None
                mut = (blocks.get(pid) or {}).get("mutation") or {}
                pc = mut.get("proccode")
                if isinstance(pc, str):
                    def_codes.add(pc)
                    aids, anames = mut.get("argumentids"), mut.get("argumentnames")
                    try:
                        na = len(json.loads(anames)) if isinstance(anames, str) else None
                        ni = len(json.loads(aids)) if isinstance(aids, str) else None
                    except json.JSONDecodeError:
                        na = ni = -1
                    if na is not None and ni is not None and na != ni:
                        errs.append(f"{t['name']}: argumentnames/ids 数不一致")
            elif op == "procedures_call":
                calls.append(b)
        for b in calls:
            pc = (b.get("mutation") or {}).get("proccode")
            if pc not in def_codes:
                errs.append(f"{t['name']}: 未バインドの procedures_call ({str(pc)[:40]})")
    return errs


def flatten(project):
    """全ターゲットの variables/lists/broadcasts を結合した辞書を返す。"""
    vs, ls, bs = {}, {}, {}
    for t in project["targets"]:
        vs.update(t.get("variables") or {})
        ls.update(t.get("lists") or {})
        bs.update(t.get("broadcasts") or {})
    return vs, ls, bs


def make_sb3(path, project):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", json.dumps(project, ensure_ascii=False))
        zf.writestr("dummy.svg", "<svg/>")


def approx(n):  # 短縮IDの文字数上限
    return n <= 4


def main():
    tmp = tempfile.mkdtemp(prefix="sb3test_")
    ok = True

    # ---------- 1) 合成プロジェクト: デフォルト設定 ----------
    sample = build_sample()
    sb3_path = os.path.join(tmp, "sample.sb3")
    out_path = os.path.join(tmp, "sample_compressed.sb3")
    make_sb3(sb3_path, sample)
    payload = compress_file(sb3_path, Options())
    assert payload["container"] == "sb3"
    with zipfile.ZipFile(io.BytesIO(payload["final_bytes"])) as zf:
        names = sorted(zf.namelist())
        out_project = json.loads(zf.read("project.json").decode("utf-8"))
        dummy = zf.read("dummy.svg")
    assert names == ["dummy.svg", "project.json"]
    assert dummy == b"<svg/>"

    errs = validate_project(out_project)
    if errs:
        ok = False
        print("[NG] 整合性エラー:")
        for e in errs[:20]:
            print("   ", e)
    else:
        print("[OK] 参照整合性（next/parent/inputs/fields/monitors）")

    st, tgt_stage, tgt_sp = out_project, out_project["targets"][0], out_project["targets"][1]
    svars, slists, sbcs = flatten(out_project)

    assert all(len(k) <= 4 for k in tgt_sp["blocks"]), "ブロックIDが短縮されていない"
    print(f"[OK] ブロックID短縮 ({len(tgt_sp['blocks'])}個)")

    cloud_kv = next((k, v) for k, v in svars.items() if v[0].startswith("\u2601"))
    plain_kv = next((k, v) for k, v in svars.items() if not v[0].startswith("\u2601"))
    new_score_id, new_score_name = plain_kv[0], plain_kv[1][0]
    assert len(cloud_kv) == 2
    assert any(v[0] == "\u2601 V2" or v[0].startswith("\u2601 ") for v in svars.values()), \
        f"クラウド変数の接頭辞が保持されていない: {svars}"
    print("[OK] クラウド変数の接頭辞保持:", [v[0] for v in svars.values()])

    blk_set = next(b for b in tgt_stage["blocks"].values()
                   if b["opcode"] == "data_setvariableto")
    assert blk_set["fields"]["VARIABLE"] == [new_score_name, new_score_id]
    mon = next(m for m in out_project["monitors"] if m["opcode"] == "data_variable")
    assert mon["id"] == new_score_id and mon["params"]["VARIABLE"] == new_score_name
    timer_mon = next(m for m in out_project["monitors"] if m["opcode"] == "sensing_timer")
    assert timer_mon["id"] == "timerMon00000000000000"
    assert all("value" not in m and "sliderMin" not in m for m in out_project["monitors"])
    print("[OK] モニター追従更新 + 既定値削除")

    first_bc = next(iter(sbcs.values()))
    new_go = first_bc[0] if isinstance(first_bc, list) else first_bc
    assert new_go.startswith("B") and len(new_go) <= 4
    bc_blk = next(b for b in tgt_stage["blocks"].values() if b["opcode"] == "event_broadcast")
    assert bc_blk["inputs"]["BROADCAST_INPUT"][1][1] == new_go
    assert bc_blk["inputs"]["BROADCAST_INPUT"][1][2] in sbcs, \
        "放送プリミティブの旧IDが残存している"
    print("[OK] 放送改名（dictキー・入力参照・フィールド同期）")

    assert "volume" not in tgt_stage and "tempo" not in tgt_stage
    for k in ("visible", "x", "y", "size", "direction", "draggable",
              "rotationStyle", "currentCostume"):
        assert k not in tgt_sp, f"{k} が削除されていない"
    assert "layerOrder" not in tgt_stage and "layerOrder" not in tgt_sp
    cos = tgt_sp["costumes"][0]
    assert "md5ext" not in cos and "bitmapResolution" not in cos \
        and "rotationCenterX" not in cos
    stage_cos = tgt_stage["costumes"][0]
    assert stage_cos["rotationCenterX"] == 240 and "md5ext" not in stage_cos
    assert "extensions" not in out_project
    assert out_project["meta"]["platform"]["name"] == "TurboWarp"
    assert "vm" not in out_project["meta"] and "agent" not in out_project["meta"]
    print("[OK] デフォルト値削除 / layerOrder正規化 / コスチューム既定値 / meta・extensions")

    sp_blocks = tgt_sp["blocks"]
    hat = next(b for b in sp_blocks.values() if b["opcode"] == "event_whenflagclicked")
    assert hat["topLevel"] is True and "shadow" not in hat
    # scratch-vm's getTopLevelScript() only stops at an explicit null parent.
    assert "parent" in hat and hat["parent"] is None
    rep = next(b for b in sp_blocks.values() if b["opcode"] == "data_variable"
               and b.get("topLevel") is not True)
    assert "topLevel" not in rep and rep.get("parent") in sp_blocks
    click = next(b for b in sp_blocks.values()
                 if b["opcode"] == "event_whenthisspriteclicked")
    assert click is not None
    cmt = tgt_sp["comments"]["cmt0001aaaaaaaaaaaaaaaa"]
    assert cmt["blockId"] in sp_blocks, "コメントのblockIdが追従していない"
    print("[OK] topLevel/shadow維持と削除、parent追従、コメントblockId追従")

    # 圧縮率がプラスであること
    assert payload["new_json_size"] < payload["orig_json_size"]
    print(f"[OK] サイズ: {payload['orig_json_size']:,}B → "
          f"{payload['new_json_size']:,}B ({payload['ratio']:.1f}% 削減)")

    # ---------- 2) オプション: click_to_stage ----------
    p2 = json.loads(json.dumps(build_sample()))
    c2 = Compressor(Options(click_to_stage=True))
    q2 = c2.run(p2)
    ops = [b["opcode"] for t in q2["targets"]
           for b in (t.get("blocks") or {}).values()]
    assert "event_whenstageclicked" in ops and "event_whenthisspriteclicked" not in ops
    assert c2.stats["click_rewrites"] >= 1
    p3 = json.loads(json.dumps(build_sample()))
    c3 = Compressor(Options(click_to_stage=False))
    q3 = c3.run(p3)
    ops3 = [b["opcode"] for t in q3["targets"]
            for b in (t.get("blocks") or {}).values()]
    assert "event_whenthisspriteclicked" in ops3
    print("[OK] オプション click_to_stage（ON/OFF）")

    # ---------- 3) オプション: shorten_ids=False ----------
    p4 = json.loads(json.dumps(build_sample()))
    c4 = Compressor(Options(shorten_ids=False))
    q4 = c4.run(p4)
    assert VID_SCORE in q4["targets"][0]["variables"]
    assert "blk00000000000000000001" in q4["targets"][0]["blocks"]
    assert "volume" not in q4["targets"][0]
    errs4 = validate_project(q4)
    assert not errs4, errs4
    print("[OK] オプション shorten_ids=False（改名せず既定値のみ削除）")

    # ---------- 4) スキーマ必須項目: 空ブロックのスプライト ----------
    p5 = json.loads(json.dumps(build_sample()))
    p5["targets"].append({
        "isStage": False, "name": "EmptySprite",
        "visible": True, "x": 0, "y": 0, "size": 100, "direction": 90,
        "draggable": False, "rotationStyle": "all around",
        "variables": {}, "lists": {}, "broadcasts": {},
        "blocks": {}, "comments": {},
        "costumes": [{"name": "c1", "dataFormat": "svg",
                      "assetId": "bcf454acf82e4504149f7ffe07081dbc",
                      "md5ext": "bcf454acf82e4504149f7ffe07081dbc.svg",
                      "rotationCenterX": 48, "rotationCenterY": 48}],
        "sounds": [], "volume": 100, "layerOrder": 2})
    c5 = Compressor(Options())
    q5 = c5.run(p5)
    assert "blocks" in q5["targets"][-1], \
        "blocks は sb3 スキーマ必須のため削除してはならない"
    assert not validate_project(q5), "整合性エラー"
    print("[OK] スキーマ必須項目(blocks)の維持")

    # ---------- 5) 頻度順ID割当 ----------
    p6 = json.loads(json.dumps(build_sample()))
    sp6 = p6["targets"][1]["blocks"]
    hot = "sp000000000000000000c"
    for i in range(80):
        holder = f"hot{i:019d}"
        sp6[holder] = {"opcode": "operator_add", "next": None,
                       "parent": None,
                       "inputs": {"OPERAND1": [3, hot, [4, "0"]]},
                       "fields": {}, "shadow": False, "topLevel": False}
    c6 = Compressor(Options())
    q6 = c6.run(p6)
    qb6 = q6["targets"][1]["blocks"]
    hot_refs = {v["inputs"]["OPERAND1"][1]
                for v in qb6.values()
                if isinstance(v, dict) and v.get("opcode") == "operator_add"
                and isinstance(v.get("inputs", {}).get("OPERAND1"), list)}
    assert hot_refs and all(len(k) == 1 for k in hot_refs), \
        f"頻出ブロックが1文字キーを得ていない: {hot_refs}"
    long_keys = [k for k in qb6 if len(k) > 1]
    assert long_keys, "全キーが1文字(ブロック数が少なすぎる)"
    print(f"[OK] 頻度順ID割当（頻出ブロック={hot_refs} が最短キー）")

    # ---------- 6) 未使用変数・リスト削除 ----------
    p7 = json.loads(json.dumps(build_sample()))
    st7 = p7["targets"][0]
    st7["variables"]["ghostVar00000000000"] = ["ghost", 0]
    st7["variables"]["ghostCloud000000000"] = ["\u2601 ghostc", 0]
    st7["lists"]["ghostList00000000000"] = ["ghostlist", []]
    p7["monitors"].append({
        "id": "ghostVar00000000000", "mode": "default",
        "opcode": "data_variable", "params": {"VARIABLE": "ghost"},
        "spriteName": None, "value": 0, "width": 0, "height": 0,
        "x": 300, "y": 300, "visible": True})
    c7 = Compressor(Options())
    q7 = c7.run(p7)
    svars7, slists7, _ = flatten(q7)
    names7 = [v[0] for v in svars7.values()]
    lnames7 = [v[0] for v in slists7.values()]
    assert "\u2601 ghostc" not in names7, f"未使用クラウド変数が残っている: {names7}"
    assert "ghostlist" not in lnames7, "未使用リストが残っている"
    # 構成: score + ☁cloudvar + local + ghost(モニター参照で保持) / mylist
    assert len(svars7) == 4, f"変数数が不正: {names7}"
    assert len(slists7) == 1, f"リスト数が不正: {lnames7}"
    assert c7.stats["vars_removed"] >= 1 and c7.stats["lists_removed"] >= 1
    errs7 = validate_project(q7)
    assert not errs7, errs7
    mon_ids7 = {m.get("id") for m in q7["monitors"]}
    all_store_ids7 = set()
    for t in q7["targets"]:
        all_store_ids7 |= set(t.get("variables") or {})
        all_store_ids7 |= set(t.get("lists") or {})
    non_data_mon = {m.get("id") for m in q7["monitors"]
                    if m.get("opcode") not in ("data_variable", "data_listcontents")}
    assert mon_ids7 <= all_store_ids7 | non_data_mon, "モニターIDが実変数と不一致"
    print(f"[OK] 未使用変数・リスト削除 "
          f"(var={c7.stats['vars_removed']} list={c7.stats['lists_removed']} 削除, "
          f"モニター参照は保持)")

    # ---------- 6b) 単独レポーター(primitive array)とID不明時の名前参照 ----------
    p7b = json.loads(json.dumps(build_sample()))
    st7b = p7b["targets"][0]
    ARR_VID = "arrVar00000000000000"
    ARR_LID = "arrList0000000000000"
    STALE_VID = "staleVar000000000000"
    SENSE_VID = "sensedVar000000000000"
    SENSE_OBJ = "sensedObjMenu000000"
    st7b["variables"][ARR_VID] = ["arrVar", 0]
    st7b["lists"][ARR_LID] = ["arrList", []]
    st7b["variables"][STALE_VID] = ["staleVar", 0]
    st7b["variables"][SENSE_VID] = ["sensed", 0]
    # 単独の変数/リストレポーターは block オブジェクトではなく配列で保存される
    st7b["blocks"]["arrVarReporter00000"] = [12, "arrVar", ARR_VID, 10, 20]
    st7b["blocks"]["arrListReporter0000"] = [13, "arrList", ARR_LID, 10, 50]
    # IDが欠落/不整合でもVMは名前で解決するため、名前側の定義を残す必要がある
    st7b["blocks"]["staleRef00000000000"] = {
        "opcode": "data_setvariableto", "next": None, "parent": None,
        "inputs": {"VALUE": [1, [10, "1"]]},
        "fields": {"VARIABLE": ["staleVar", "missing-id"]},
        "shadow": False, "topLevel": False,
    }
    # sensing_of は PROPERTY の変数名で実行時に参照する(IDを持たない)。
    # OBJECT は sensing_of_object_menu の shadow ブロックを入力に持つ。
    st7b["blocks"]["sensingOf000000000"] = {
        "opcode": "sensing_of", "next": None, "parent": None,
        "inputs": {"OBJECT": [1, SENSE_OBJ]},
        "fields": {"PROPERTY": ["sensed", None]},
        "shadow": False, "topLevel": True, "x": 200, "y": 200,
    }
    st7b["blocks"][SENSE_OBJ] = {
        "opcode": "sensing_of_object_menu", "next": None,
        "parent": "sensingOf000000000", "inputs": {},
        "fields": {"OBJECT": ["_stage_", None]},
        "shadow": True, "topLevel": False,
    }
    c7b = Compressor(Options())
    q7b = c7b.run(p7b)
    svars7b, slists7b, _ = flatten(q7b)
    arr_v = next(b for b in q7b["targets"][0]["blocks"].values()
                 if isinstance(b, list) and b[0] == 12)
    arr_l = next(b for b in q7b["targets"][0]["blocks"].values()
                 if isinstance(b, list) and b[0] == 13)
    assert arr_v[2] in svars7b and svars7b[arr_v[2]][0] == arr_v[1], \
        f"単独変数レポーターが追従していない: {arr_v}"
    assert arr_l[2] in slists7b and slists7b[arr_l[2]][0] == arr_l[1], \
        f"単独リストレポーターが追従していない: {arr_l}"
    assert len(svars7b) == 6, \
        f"単独レポーター/名前参照の変数が削除された: {[v[0] for v in svars7b.values()]}"
    assert len(slists7b) == 2, \
        f"単独レポーター/モニターのリストが削除された: {[v[0] for v in slists7b.values()]}"
    var_field_ids = {b["fields"]["VARIABLE"][1]
                     for b in q7b["targets"][0]["blocks"].values()
                     if isinstance(b, dict)
                     and isinstance((b.get("fields") or {}).get("VARIABLE"), list)}
    assert var_field_ids <= set(svars7b), "名前参照の変数IDが定義に存在しない"
    sense_block = next(b for b in q7b["targets"][0]["blocks"].values()
                       if isinstance(b, dict) and b.get("opcode") == "sensing_of")
    assert sense_block["fields"]["PROPERTY"][0] == c7b.var_map[SENSE_VID][1], \
        f"sensing_of の PROPERTY が改名に追従していない: {sense_block['fields']}"
    errs7b = validate_project(q7b)
    assert not errs7b, errs7b
    print("[OK] 単独レポーター保持・改名 / ID不明時の名前フォールバック / sensing_of 参照")

    # ---------- 7) 定義名・引数名の短縮 ----------
    p8 = json.loads(json.dumps(build_sample()))
    c8 = Compressor(Options())
    q8 = c8.run(p8)
    sb8 = q8["targets"][1]["blocks"]
    proto8 = next(b for b in sb8.values() if b["opcode"] == "procedures_prototype")
    call8 = next(b for b in sb8.values() if b["opcode"] == "procedures_call")
    pm, cm = proto8["mutation"], call8["mutation"]
    assert pm["proccode"] != "\u30d7\u30ed\u30b7\u30fc\u30b8\u30e3 %s", \
        f"定義名が短縮されていない: {pm['proccode']}"
    assert cm["proccode"] == pm["proccode"], "呼び出し側のproccodeが追従していない"
    anames = json.loads(pm["argumentnames"])
    assert anames == ["a0"], f"引数名が短縮されていない: {anames}"
    assert json.loads(pm["argumentids"]) == ["ARG1"], "argumentids が変更されている"
    rep = next(b for b in sb8.values()
               if isinstance(b, dict) and b.get("opcode") == "argument_reporter_string_number"
               and b.get("topLevel") is not True and b.get("parent"))
    assert rep["fields"]["VALUE"][0] == "a0", \
        f"本文中の引数報告ブロックが追従していない: {rep['fields']['VALUE']}"
    assert pm.get("warp") is True
    errs8 = validate_project(q8)
    assert not errs8, errs8
    print(f"[OK] 定義名・引数名の短縮 (proccode='{pm['proccode']}', "
          f"args={anames}, 定義 {c8.stats['procs_renamed']}件)")

    # 重複proccode定義は触らない(バインド曖昧回避)+衝突なし
    p9 = json.loads(json.dumps(build_sample()))
    src_proto = next(b for b in p9["targets"][1]["blocks"].values()
                     if b.get("opcode") == "procedures_prototype")
    dup_proto = json.loads(json.dumps(src_proto))
    dup_hat = {"opcode": "procedures_definition", "next": None, "parent": None,
               "inputs": {"custom_block": [1, "DUPPROTO000000000"]},
               "fields": {}, "shadow": False, "topLevel": True, "x": 0, "y": 400}
    dup_proto["parent"] = "DUPHAT00000000000000"
    p9["targets"][1]["blocks"]["DUPHAT00000000000000"] = dup_hat
    p9["targets"][1]["blocks"]["DUPPROTO000000000"] = dup_proto
    c9 = Compressor(Options())
    q9 = c9.run(p9)
    sb9 = q9["targets"][1]["blocks"]
    codes = [b["mutation"]["proccode"] for b in sb9.values()
             if isinstance(b, dict) and b.get("opcode") == "procedures_prototype"]
    # 重複グループはバインド曖昧回避のため改名されない(元のまま維持)
    assert codes.count("do %s") == 2 and len(set(codes)) == 1, \
        f"重複proccodeの扱いが不正: {codes}"
    errs9 = validate_project(q9)
    assert not errs9, errs9
    print("[OK] 重複proccode定義の扱い（改名せず衝突なし）")

    # ---------- 8) 実ファイル: sb3compressor.sb3 ----------
    real = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sb3compressor.sb3")
    if os.path.isfile(real):
        rp = compress_file(real, Options())
        with zipfile.ZipFile(io.BytesIO(rp["final_bytes"])) as zf:
            real_out = json.loads(zf.read("project.json").decode("utf-8"))
            src = zipfile.ZipFile(real)
            src_assets = sorted(i.filename for i in src.infolist()
                                if i.filename != "project.json")
            dst_assets = sorted(n for n in zf.namelist() if n != "project.json")
            assert src_assets == dst_assets, "アセットが一致しない"
            src.close()
        errs_r = validate_project(real_out)
        if errs_r:
            ok = False
            print("[NG] 実ファイル整合性エラー:", errs_r[:10])
        else:
            print(f"[OK] 実ファイル sb3compressor.sb3: "
                  f"{rp['orig_json_size']:,}B → {rp['new_json_size']:,}B "
                  f"({rp['ratio']:.1f}% 削減, 最終.sb3 "
                  f"{rp['new_file_size']:,}B)")
            print("     内訳:", rp["stats"])

    # ---------- 6) CLI 動作 ----------
    r = subprocess.run([sys.executable, os.path.abspath("sb3_compressor.py"),
                        sb3_path, out_path],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    assert os.path.isfile(out_path)
    with zipfile.ZipFile(out_path) as zf:
        json.loads(zf.read("project.json"))
    print("[OK] CLI モード（終了コード0, 出力.sb3検証済み）")

    print("\n" + ("ALL TESTS PASSED" if ok else "FAILURES DETECTED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

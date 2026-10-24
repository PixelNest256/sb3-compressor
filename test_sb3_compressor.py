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
        # A real receiver so the broadcast is not treated as a no-op.
        "blk00000000000000000005": blk("event_whenbroadcastreceived",
                                       topLevel=True, x=0, y=600,
                                       next="blk00000000000000000006",
                                       fields={"BROADCAST_OPTION": ["go!", BID_GO]}),
        "blk00000000000000000006": blk("motion_movesteps",
                                       parent="blk00000000000000000005",
                                       inputs={"STEPS": [1, [4, "1"]]}),
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


def build_feature_sample():
    """新機能（未表示ストア削除・初期値・到達不能・重複・隠れ既定値）の検証用。"""
    def blk(opcode, **kw):
        b = {"opcode": opcode, "next": None, "parent": None, "inputs": {},
             "fields": {}, "shadow": False, "topLevel": False}
        b.update(kw)
        return b

    V = {
        "keepRead": "vKeepRead0000000000000",
        "hiddenOnly": "vHiddenOnly00000000000",
        "visibleOnly": "vVisibleOnly0000000000",
        "writeOnly": "vWriteOnly000000000000",
        "initVar": "vInitVar00000000000000",
        "selfVar": "vSelfVar00000000000000",
        "readFirst": "vReadFirst000000000000",
        "sensedVar": "vSensedVar000000000000",
        "looseVar": "vLooseVar0000000000000",
        "orphanVar": "vOrphanVar000000000000",
    }
    L = {
        "hiddenListOnly": "lHiddenOnly00000000000",
        "visibleListOnly": "lVisibleOnly0000000000",
        "readList": "lReadList0000000000000",
        "initList": "lInitList0000000000000",
        "appendList": "lAppendList00000000000",
        "deleteOnlyList": "lDeleteOnly00000000000",
        "readOnlyList": "lReadOnly000000000000",
    }
    B = {
        "usedMsg": "bUsedMsg00000000000000",
        "unusedMsg": "bUnusedMsg000000000000",
    }

    blocks = {}
    comments = {}

    def add_script(hat_id, specs, x=0, y=0):
        blocks[hat_id] = blk("event_whenflagclicked", topLevel=True, x=x, y=y)
        prev = hat_id
        for i, (op, inputs, fields) in enumerate(specs):
            bid = f"{hat_id}_{i}"
            blocks[prev]["next"] = bid
            blocks[bid] = blk(op, parent=prev, inputs=inputs, fields=fields)
            prev = bid
        return prev

    def add_reporter(bid, op, parent, fields=None, inputs=None):
        blocks[bid] = blk(op, parent=parent, fields=fields or {},
                          inputs=inputs or {})

    # 読み取り専用（書き込みなし）だが、コードから読まれるので保持される。
    add_reporter("keepReadRep0000000000", "data_variable", "flagKeepRead000000_0",
                 {"VARIABLE": ["keepRead", V["keepRead"]]})
    add_script("flagKeepRead000000", [
        ("looks_say", {"MESSAGE": [3, "keepReadRep0000000000", [10, ""]]}, {}),
    ], x=0, y=0)

    # 書き込みのみ（読み取りなし）。初期値は空白にできる。
    add_script("flagWriteOnly000000", [
        ("data_setvariableto", {"VALUE": [1, [10, "4"]]},
         {"VARIABLE": ["writeOnly", V["writeOnly"]]}),
    ], x=0, y=300)

    # 読み取りより先に初期化。初期値を空白にできる。
    add_reporter("initVarRep00000000000", "data_variable", "flagInit00000000000_1",
                 {"VARIABLE": ["initVar", V["initVar"]]})
    add_script("flagInit00000000000", [
        ("data_setvariableto", {"VALUE": [1, [10, "0"]]},
         {"VARIABLE": ["initVar", V["initVar"]]}),
        ("looks_say", {"MESSAGE": [3, "initVarRep00000000000", [10, ""]]}, {}),
    ], x=0, y=600)

    # 自分自身を読む change は初期化ではない。
    add_reporter("selfVarRep00000000000", "data_variable", "flagSelf00000000000_1",
                 {"VARIABLE": ["selfVar", V["selfVar"]]})
    add_script("flagSelf00000000000", [
        ("data_changevariableby", {"VALUE": [1, [4, "1"]]},
         {"VARIABLE": ["selfVar", V["selfVar"]]}),
        ("looks_say", {"MESSAGE": [3, "selfVarRep00000000000", [10, ""]]}, {}),
    ], x=0, y=900)

    # 読み取りが先。初期値を保持。
    add_reporter("readFirstRep000000000", "data_variable", "flagReadFirst0000000_0",
                 {"VARIABLE": ["readFirst", V["readFirst"]]})
    add_script("flagReadFirst0000000", [
        ("looks_say", {"MESSAGE": [3, "readFirstRep000000000", [10, ""]]}, {}),
        ("data_setvariableto", {"VALUE": [1, [10, "0"]]},
         {"VARIABLE": ["readFirst", V["readFirst"]]}),
    ], x=0, y=1200)

    # sensing_of は PROPERTY 名で読む。表示ではないが読み取りなので保持。
    blocks["senseMenu00000000000"] = blk(
        "sensing_of_object_menu", parent="senseBlock000000000",
        fields={"OBJECT": ["_stage_", None]}, shadow=True)
    blocks["senseBlock000000000"] = blk(
        "sensing_of", topLevel=True, x=300, y=300,
        inputs={"OBJECT": [1, "senseMenu00000000000"]},
        fields={"PROPERTY": ["sensedVar", None]})

    # リストの読み取り・初期化・追加。
    def add_list_read(bid, parent, lid, lname):
        add_reporter(bid, "data_itemoflist", parent,
                     {"LIST": [lname, lid]}, {"INDEX": [1, [7, "1"]]})

    add_list_read("readListRep000000000", "flagReadList00000000_0", L["readList"], "readList")
    add_script("flagReadList00000000", [
        ("looks_say", {"MESSAGE": [3, "readListRep000000000", [10, ""]]}, {}),
    ], x=0, y=1500)

    add_list_read("initListRep000000000", "flagInitList00000000_1", L["initList"], "initList")
    add_script("flagInitList00000000", [
        ("data_deletealloflist", {}, {"LIST": ["initList", L["initList"]]}),
        ("looks_say", {"MESSAGE": [3, "initListRep000000000", [10, ""]]}, {}),
    ], x=0, y=1800)

    add_list_read("appendListRep0000000", "flagAppendList000000_1", L["appendList"], "appendList")
    add_script("flagAppendList000000", [
        ("data_addtolist", {"ITEM": [1, [10, "new"]]},
         {"LIST": ["appendList", L["appendList"]]}),
        ("looks_say", {"MESSAGE": [3, "appendListRep0000000", [10, ""]]}, {}),
    ], x=0, y=2100)

    add_script("flagDeleteOnly000000", [
        ("data_deletealloflist", {}, {"LIST": ["deleteOnlyList", L["deleteOnlyList"]]}),
    ], x=0, y=2400)

    add_list_read("readOnlyListRep00000", "flagReadOnlyList0000_0",
                  L["readOnlyList"], "readOnlyList")
    add_script("flagReadOnlyList0000", [
        ("looks_say", {"MESSAGE": [3, "readOnlyListRep00000", [10, ""]]}, {}),
    ], x=0, y=2700)

    # 隠れ既定値（演算ブロックに覆われた go to の X 既定値）。
    blocks["goReporter0000000000"] = blk(
        "operator_add", parent="flagGo0000000000000_0",
        inputs={"OPERAND1": [1, [10, "1"]], "OPERAND2": [1, [10, "2"]]})
    add_script("flagGo0000000000000", [
        ("motion_gotoxy",
         {"X": [3, "goReporter0000000000", [4, "0"]],
          "Y": [1, [4, "0"]]}, {}),
    ], x=500, y=0)

    # 到達不能: 呼び出されない定義、孤立ブロック、ルーズなスタック、
    # 送信されない放送のレシーバー、使われないメッセージ。
    blocks["deadDef000000000000"] = blk(
        "procedures_definition", topLevel=True, x=0, y=3200,
        next="deadBody000000000000",
        inputs={"custom_block": [1, "deadProto0000000000"]})
    blocks["deadProto0000000000"] = blk(
        "procedures_prototype", parent="deadDef000000000000",
        mutation={"proccode": "dead", "warp": False,
                  "argumentids": "[]", "argumentnames": "[]",
                  "argumentdefaults": "[]"})
    blocks["deadBody000000000000"] = blk(
        "motion_movesteps", parent="deadDef000000000000",
        inputs={"STEPS": [1, [4, "1"]]})

    blocks["orphan0000000000000"] = blk(
        "data_setvariableto", inputs={"VALUE": [1, [10, "1"]]},
        fields={"VARIABLE": ["orphanVar", V["orphanVar"]]})
    blocks["looseStack0000000000"] = blk(
        "data_setvariableto", topLevel=True, x=0, y=3500,
        inputs={"VALUE": [1, [10, "1"]]},
        fields={"VARIABLE": ["looseVar", V["looseVar"]]})

    blocks["recvNoSendHat00000000"] = blk(
        "event_whenbroadcastreceived", topLevel=True, x=0, y=3800,
        next="recvNoSendBody00000",
        fields={"BROADCAST_OPTION": ["unusedMsg", B["unusedMsg"]]})
    blocks["recvNoSendBody00000"] = blk(
        "motion_movesteps", parent="recvNoSendHat00000000",
        inputs={"STEPS": [1, [4, "1"]]})

    blocks["recvKeptHat0000000000"] = blk(
        "event_whenbroadcastreceived", topLevel=True, x=0, y=4100,
        next="recvKeptBody00000000",
        fields={"BROADCAST_OPTION": ["usedMsg", B["usedMsg"]]})
    blocks["recvKeptBody00000000"] = blk(
        "motion_movesteps", parent="recvKeptHat0000000000",
        inputs={"STEPS": [1, [4, "1"]]})

    add_script("flagSendKept00000000", [
        ("event_broadcast",
         {"BROADCAST_INPUT": [1, [11, "usedMsg", B["usedMsg"]]]}, {}),
    ], x=0, y=4400)

    comments["commentOrphan000000"] = {
        "blockId": "orphan0000000000000", "x": 0, "y": 0,
        "width": 100, "height": 50, "minimized": False, "text": "orphan"}
    comments["commentKept00000000"] = {
        "blockId": "flagKeepRead000000_0", "x": 0, "y": 0,
        "width": 100, "height": 50, "minimized": False, "text": "kept"}
    # ワークスペースに直接置かれたコメントはスクリプトに属さないため保持する。
    comments["commentFree00000000"] = {
        "blockId": None, "x": 300, "y": 0,
        "width": 120, "height": 60, "minimized": False, "text": "free note"}

    stage = {
        "isStage": True, "name": "Stage",
        "variables": {
            V["keepRead"]: ["keepRead", 10],
            V["hiddenOnly"]: ["hiddenOnly", 11],
            V["visibleOnly"]: ["visibleOnly", 12],
            V["writeOnly"]: ["writeOnly", 13],
            V["initVar"]: ["initVar", 99],
            V["selfVar"]: ["selfVar", 5],
            V["readFirst"]: ["readFirst", 6],
            V["sensedVar"]: ["sensedVar", 7],
            V["looseVar"]: ["looseVar", 8],
            V["orphanVar"]: ["orphanVar", 9],
        },
        "lists": {
            L["hiddenListOnly"]: ["hiddenListOnly", [1]],
            L["visibleListOnly"]: ["visibleListOnly", [2]],
            L["readList"]: ["readList", ["r"]],
            L["initList"]: ["initList", ["x"]],
            L["appendList"]: ["appendList", ["y"]],
            L["deleteOnlyList"]: ["deleteOnlyList", ["z"]],
            L["readOnlyList"]: ["readOnlyList", ["q"]],
        },
        "broadcasts": {
            B["usedMsg"]: ["usedMsg"],
            B["unusedMsg"]: ["unusedMsg"],
        },
        "blocks": blocks, "comments": comments,
        "costumes": [], "sounds": [],
    }

    # 同一コードを2箇所に置く（短い列もサイズが減れば抽出対象）。
    dup_blocks = {}
    for si in range(2):
        hat = f"dupHat{si}"
        dup_blocks[hat] = blk("event_whenflagclicked", topLevel=True,
                              x=0, y=si * 400)
        prev = hat
        for j in range(12):
            bid = f"dup{si}_{j}"
            dup_blocks[prev]["next"] = bid
            dup_blocks[bid] = blk("motion_movesteps", parent=prev,
                                  inputs={"STEPS": [1, [4, "10"]]})
            prev = bid
    dup_sprite = {
        "isStage": False, "name": "DupSprite",
        "variables": {}, "lists": {}, "broadcasts": {},
        "blocks": dup_blocks, "comments": {}, "costumes": [], "sounds": [],
    }

    monitors = [
        {"id": V["hiddenOnly"], "mode": "default", "opcode": "data_variable",
         "params": {"VARIABLE": "hiddenOnly"}, "spriteName": None,
         "visible": False, "x": 0, "y": 0},
        {"id": L["hiddenListOnly"], "mode": "list", "opcode": "data_listcontents",
         "params": {"LIST": "hiddenListOnly"}, "spriteName": None,
         "visible": False, "x": 0, "y": 0},
        {"id": V["visibleOnly"], "mode": "default", "opcode": "data_variable",
         "params": {"VARIABLE": "visibleOnly"}, "spriteName": None,
         "visible": True, "x": 0, "y": 100},
        {"id": L["visibleListOnly"], "mode": "list", "opcode": "data_listcontents",
         "params": {"LIST": "visibleListOnly"}, "spriteName": None,
         "visible": True, "x": 0, "y": 200},
    ]
    return {
        "targets": [stage, dup_sprite],
        "monitors": monitors,
        "extensions": [],
        "meta": {"semver": "3.0.0"},
    }


def build_warp_duplicate_sample():
    """warp 定義内の同一コードは抽出してはならない（画面更新が変わる）。"""
    def blk(opcode, **kw):
        b = {"opcode": opcode, "next": None, "parent": None, "inputs": {},
             "fields": {}, "shadow": False, "topLevel": False}
        b.update(kw)
        return b

    blocks = {}
    blocks["warpDef00000000000"] = blk(
        "procedures_definition", topLevel=True, x=0, y=0, next="warpBody0",
        inputs={"custom_block": [1, "warpProto0000000000"]})
    blocks["warpProto0000000000"] = blk(
        "procedures_prototype", parent="warpDef00000000000", shadow=True,
        mutation={"tagName": "mutation", "children": [],
                  "proccode": "warpy", "argumentids": "[]",
                  "argumentnames": "[]", "argumentdefaults": "[]",
                  "warp": "true"})
    prev = "warpDef00000000000"
    for i in range(12):
        bid = f"warpBody{i}"
        blocks[prev]["next"] = bid
        blocks[bid] = blk("motion_movesteps", parent=prev,
                          inputs={"STEPS": [1, [4, "1"]]})
        prev = bid

    # 同じ本体を持つ warp 定義をもう 1 つ置く。warp 同士なら安全に抽出できる。
    blocks["warpDefB0000000000"] = blk(
        "procedures_definition", topLevel=True, x=0, y=200, next="warpBBody0",
        inputs={"custom_block": [1, "warpProtoB000000000"]})
    blocks["warpProtoB000000000"] = blk(
        "procedures_prototype", parent="warpDefB0000000000", shadow=True,
        mutation={"tagName": "mutation", "children": [],
                  "proccode": "warpy", "argumentids": "[]",
                  "argumentnames": "[]", "argumentdefaults": "[]",
                  "warp": "true"})
    prev = "warpDefB0000000000"
    for i in range(12):
        bid = f"warpBBody{i}"
        blocks[prev]["next"] = bid
        blocks[bid] = blk("motion_movesteps", parent=prev,
                          inputs={"STEPS": [1, [4, "1"]]})
        prev = bid

    # 同じ 12 ブロックが通常スクリプトにも 1 回だけ存在する。
    blocks["normalHat0000000000"] = blk("event_whenflagclicked",
                                        topLevel=True, x=0, y=400)
    prev = "normalHat0000000000"
    for i in range(12):
        bid = f"normalBody{i}"
        blocks[prev]["next"] = bid
        blocks[bid] = blk("motion_movesteps", parent=prev,
                          inputs={"STEPS": [1, [4, "1"]]})
        prev = bid

    # 呼び出しがないと定義自体が到達不能で消えるため、呼び出しを置く。
    blocks["callHat000000000000"] = blk("event_whenflagclicked",
                                        topLevel=True, x=0, y=800,
                                        next="callWarp00000000000")
    blocks["callWarp00000000000"] = blk(
        "procedures_call", parent="callHat000000000000",
        mutation={"tagName": "mutation", "children": [],
                  "proccode": "warpy", "argumentids": "[]",
                  "warp": "false"})

    return {
        "targets": [{
            "isStage": True, "name": "Stage",
            "variables": {}, "lists": {}, "broadcasts": {},
            "blocks": blocks, "comments": {}, "costumes": [], "sounds": [],
        }],
        "monitors": [], "extensions": [], "meta": {"semver": "3.0.0"},
    }


def build_argument_duplicate_sample(mode="same_def"):
    """引数付き定義内の重複ブロックを、引数を引き継ぐ定義へ抽出できるか検証する。

    mode:
      ``same_def``       - 同じ定義内の重複で x / flag を使用（抽出される）
      ``different_defs`` - 別々の定義で同じ引数名を使用（定義が違うので抽出しない）
      ``no_args``        - 引数付き定義内だが、重複コードは引数を使用しない（抽出される）
      ``undeclared``     - 定義にない引数名のレポーターを使用（抽出しない）
    """
    def blk(opcode, **kw):
        b = {"opcode": opcode, "next": None, "parent": None, "inputs": {},
             "fields": {}, "shadow": False, "topLevel": False}
        b.update(kw)
        return b

    VID_RES = "gVres00000000000000"
    VID_CNT = "gVcnt00000000000000"
    blocks = {}
    counter = [0]

    def nid(prefix="argN"):
        counter[0] += 1
        return f"{prefix}{counter[0]:03d}"

    def make_chain(prev, x_name, flag_name, use_x, use_flag):
        seq = []
        state = {"prev": prev}

        def emit(opcode, inputs=None, fields=None):
            bid = nid()
            blocks[bid] = blk(opcode, parent=state["prev"],
                              inputs=inputs or {}, fields=fields or {})
            if (isinstance(state["prev"], str)
                    and state["prev"] in blocks):
                blocks[state["prev"]]["next"] = bid
            state["prev"] = bid
            seq.append(bid)
            return bid

        def nested(opcode, parent, inputs=None, fields=None):
            bid = nid()
            blocks[bid] = blk(opcode, parent=parent, inputs=inputs or {},
                              fields=fields or {})
            return bid

        def arg_reporter(parent, name, is_bool=False):
            bid = nid()
            blocks[bid] = blk(
                ("argument_reporter_boolean" if is_bool
                 else "argument_reporter_string_number"),
                parent=parent, fields={"VALUE": [name, None]})
            return bid

        def set_res(addend):
            body = emit("data_setvariableto",
                        fields={"VARIABLE": ["res", VID_RES]})
            if use_x:
                add = nested("operator_add", body, inputs={
                    "NUM1": [1, [4, "0"]],
                    "NUM2": [1, [4, str(addend)]]})
                rep = arg_reporter(add, x_name)
                blocks[add]["inputs"]["NUM1"] = [3, rep, [4, ""]]
                blocks[body]["inputs"]["VALUE"] = [3, add, [10, ""]]
            else:
                blocks[body]["inputs"]["VALUE"] = [1, [10, str(addend)]]

        def change_cnt():
            emit("data_changevariableby",
                 inputs={"VALUE": [1, [4, "1"]]},
                 fields={"VARIABLE": ["cnt", VID_CNT]})

        def if_flag(amount):
            body = emit("control_if")
            if use_flag:
                rep = arg_reporter(body, flag_name, True)
                blocks[body]["inputs"]["CONDITION"] = [2, rep]
            else:
                eq = nested("operator_equals", body, inputs={
                    "OPERAND1": [1, [4, "1"]],
                    "OPERAND2": [1, [4, "1"]]})
                blocks[body]["inputs"]["CONDITION"] = [2, eq]
            sub = nested("data_changevariableby", body,
                         inputs={"VALUE": [1, [4, str(amount)]]},
                         fields={"VARIABLE": ["res", VID_RES]})
            blocks[body]["inputs"]["SUBSTACK"] = [2, sub]

        set_res(1)
        change_cnt()
        if_flag(10)
        change_cnt()
        set_res(2)
        if_flag(20)
        change_cnt()
        set_res(3)
        if_flag(30)
        change_cnt()
        return seq[0], seq[-1]

    def add_def(prefix, proccode, args, x_name, flag_name,
                use_x, use_flag, chain_count=1):
        def_id = f"{prefix}Def"
        proto_id = f"{prefix}Proto"
        blocks[def_id] = blk("procedures_definition", topLevel=True,
                             x=0, y=100 + counter[0] * 20,
                             inputs={"custom_block": [1, proto_id]})
        arg_ids = [a[0] for a in args]
        blocks[proto_id] = blk(
            "procedures_prototype", parent=def_id, shadow=True,
            mutation={
                "tagName": "mutation", "children": [],
                "proccode": proccode,
                "argumentids": json.dumps(arg_ids, separators=(",", ":")),
                "argumentnames": json.dumps([a[1] for a in args],
                                            ensure_ascii=False,
                                            separators=(",", ":")),
                "argumentdefaults": json.dumps([a[2] for a in args],
                                               separators=(",", ":")),
                "warp": "false",
            })
        prev = def_id
        for _ in range(chain_count):
            _, prev = make_chain(prev, x_name, flag_name, use_x, use_flag)
        return def_id

    hat = "argHat0001"
    blocks[hat] = blk("event_whenflagclicked", topLevel=True, x=400, y=0)
    prev = hat

    def add_call(proccode, arg_ids, values):
        nonlocal prev
        call = nid("argCall")
        inputs = {}
        for aid, (kind, value) in zip(arg_ids, values):
            if kind == "bool":
                eq = nid("argEq")
                blocks[eq] = blk("operator_equals", parent=call, inputs={
                    "OPERAND1": [1, [4, str(value[0])]],
                    "OPERAND2": [1, [4, str(value[1])]]})
                inputs[aid] = [2, eq]
            else:
                inputs[aid] = [1, [10, str(value)]]
        blocks[call] = blk(
            "procedures_call", parent=prev, inputs=inputs,
            mutation={"tagName": "mutation", "children": [],
                      "proccode": proccode,
                      "argumentids": json.dumps(arg_ids, separators=(",", ":")),
                      "warp": "false"})
        blocks[prev]["next"] = call
        prev = call

    if mode == "same_def":
        add_def("sameA", "proc %s %b",
                [("AIDX", "x", ""), ("AIDF", "flag", False)],
                "x", "flag", True, True, chain_count=2)
        add_call("proc %s %b", ["AIDX", "AIDF"], [("text", 5), ("bool", (1, 1))])
        add_call("proc %s %b", ["AIDX", "AIDF"], [("text", 2), ("bool", (1, 2))])
    elif mode == "different_defs":
        add_def("diffA", "f %s", [("AIDX", "x", "")],
                "x", "flag", True, False)
        add_def("diffB", "g %s", [("BIDX", "x", "")],
                "x", "flag", True, False)
        add_call("f %s", ["AIDX"], [("text", 1)])
        add_call("g %s", ["BIDX"], [("text", 2)])
    elif mode == "no_args":
        add_def("noaA", "f %s", [("AIDX", "unused", "")],
                "x", "flag", False, False)
        add_def("noaB", "g %s", [("BIDX", "unused", "")],
                "x", "flag", False, False)
        add_call("f %s", ["AIDX"], [("text", 1)])
        add_call("g %s", ["BIDX"], [("text", 2)])
    elif mode == "undeclared":
        add_def("undA", "f", [], "x", "flag", True, False,
                chain_count=2)
        add_call("f", [], [])
    else:
        raise ValueError(mode)

    return {
        "targets": [{
            "isStage": True, "name": "Stage",
            "variables": {VID_RES: ["res", 0], VID_CNT: ["cnt", 0]},
            "lists": {}, "broadcasts": {},
            "blocks": blocks, "comments": {},
            "costumes": [{
                "name": "backdrop1", "dataFormat": "svg",
                "assetId": "cd21514d0531fdffb22204e0ec5ed84a",
                "md5ext": "cd21514d0531fdffb22204e0ec5ed84a.svg",
                "rotationCenterX": 240, "rotationCenterY": 180,
            }],
            "sounds": [], "currentCostume": 0, "volume": 100, "tempo": 60,
            "videoTransparency": 50, "videoState": "on",
            "textToSpeechLanguage": None, "layerOrder": 0,
        }],
        "monitors": [], "extensions": [], "meta": {"semver": "3.0.0"},
    }


def build_reporter_duplicate_sample():
    """レポーター（演算ブロック）自体を重複抽出してはならない。

    レポーターを新しい定義の本体へ移すと「積み木ブロック」として扱われ、
    スクリプトのコンパイルに失敗する。同じ演算サブツリーが5回現れても、
    スタック列だけを抽出対象にする必要がある。
    """
    def blk(opcode, **kw):
        b = {"opcode": opcode, "next": None, "parent": None, "inputs": {},
             "fields": {}, "shadow": False, "topLevel": False}
        b.update(kw)
        return b

    var_ids = {f"v{i}": f"repVar{i:016d}" for i in range(5)}
    src1_id = "repSrc1aaaaaaaaaaaa"
    src2_id = "repSrc2aaaaaaaaaaaa"
    variables = {vid: [f"v{i}", 0] for i, vid in
                 ((int(k[1:]), v) for k, v in var_ids.items())}
    variables[src1_id] = ["src1", 1]
    variables[src2_id] = ["src2", 2]

    blocks = {}
    hat = "repHat00000000000000"
    blocks[hat] = blk("event_whenflagclicked", topLevel=True, x=0, y=0)
    prev = hat
    for i in range(5):
        sid = f"repSet{i:016d}"
        blocks[sid] = blk("data_setvariableto", parent=prev,
                          fields={"VARIABLE": [f"v{i}", var_ids[f"v{i}"]]})
        blocks[prev]["next"] = sid
        prev = sid

        aid = f"repAdd{i:016d}"
        blocks[aid] = blk("operator_add", parent=sid, inputs={
            "NUM1": [3, f"repR1{i:016d}", [4, ""]],
            "NUM2": [3, f"repR2{i:016d}", [4, ""]],
        })
        blocks[sid]["inputs"]["VALUE"] = [3, aid, [10, ""]]
        blocks[f"repR1{i:016d}"] = blk(
            "data_variable", parent=aid,
            fields={"VARIABLE": ["src1", src1_id]})
        blocks[f"repR2{i:016d}"] = blk(
            "data_variable", parent=aid,
            fields={"VARIABLE": ["src2", src2_id]})

    return {
        "targets": [{
            "isStage": True, "name": "Stage",
            "variables": variables, "lists": {}, "broadcasts": {},
            "blocks": blocks, "comments": {},
            "costumes": [{
                "name": "backdrop1", "dataFormat": "svg",
                "assetId": "cd21514d0531fdffb22204e0ec5ed84a",
                "md5ext": "cd21514d0531fdffb22204e0ec5ed84a.svg",
                "rotationCenterX": 240, "rotationCenterY": 180,
            }],
            "sounds": [], "currentCostume": 0, "volume": 100, "tempo": 60,
            "videoTransparency": 50, "videoState": "on",
            "textToSpeechLanguage": None, "layerOrder": 0,
        }],
        "monitors": [], "extensions": [], "meta": {"semver": "3.0.0"},
    }


def build_near_duplicate_sample(mode="literals"):
    """ほぼ同じブロックを、リテラル差分だけ引数にして共有できるか検証する。

    mode:
      ``literals`` - 3 つの goto が数値リテラルだけ異なる（抽出される）
      ``field``    - 数値リテラルに加えて三角関数のプルダウンも異なる
                     （フィールドは引数化できないため抽出しない）
    """
    def blk(opcode, **kw):
        b = {"opcode": opcode, "next": None, "parent": None, "inputs": {},
             "fields": {}, "shadow": False, "topLevel": False}
        b.update(kw)
        return b

    blocks = {}
    hat = "nearHat00000000000"
    blocks[hat] = blk("event_whenflagclicked", topLevel=True, x=0, y=0)
    prev = hat

    def make_chain(kind, idx, lits, mathop=None):
        leaf = f"near{kind}Leaf{idx:02d}"
        blocks[leaf] = blk("sensing_mousex" if kind == "X"
                           else "sensing_mousey")
        cur = leaf
        if mathop is not None:
            mid = f"near{kind}Math{idx:02d}"
            blocks[mid] = blk("operator_mathop",
                              fields={"OPERATOR": [mathop, None]},
                              inputs={"NUM": [3, leaf, [4, ""]]})
            blocks[leaf]["parent"] = mid
            cur = mid
        for j, lit in enumerate(lits):
            aid = f"near{kind}Add{idx:02d}_{j}"
            blocks[aid] = blk("operator_add", inputs={
                "NUM1": [3, cur, [4, ""]],
                "NUM2": [1, [4, lit]],
            })
            blocks[cur]["parent"] = aid
            cur = aid
        return cur

    def add_gotoxy(idx, xs, ys, mathop=None):
        nonlocal prev
        gid = f"nearGo{idx:02d}"
        blocks[gid] = blk("motion_gotoxy", parent=prev)
        blocks[prev]["next"] = gid
        prev = gid
        xcur = make_chain("X", idx, xs, mathop)
        ycur = make_chain("Y", idx, ys)
        blocks[gid]["inputs"] = {"X": [3, xcur, [4, ""]],
                                 "Y": [3, ycur, [4, ""]]}
        blocks[xcur]["parent"] = gid
        blocks[ycur]["parent"] = gid

    if mode == "field":
        add_gotoxy(0, ["1", "2", "3", "4", "5"], ["6", "7", "8"],
                   mathop="sin")
        add_gotoxy(1, ["1", "2", "3", "4", "9"], ["6", "7", "10"],
                   mathop="cos")
    else:
        add_gotoxy(0, ["1", "2", "3", "4", "5"], ["6", "7", "8"])
        add_gotoxy(1, ["1", "2", "3", "4", "5"], ["6", "7", "9"])
        add_gotoxy(2, ["10", "2", "3", "4", "5"], ["6", "7", "8"])

    return {
        "targets": [{
            "isStage": True, "name": "Stage",
            "variables": {}, "lists": {}, "broadcasts": {},
            "blocks": blocks, "comments": {},
            "costumes": [{
                "name": "backdrop1", "dataFormat": "svg",
                "assetId": "cd21514d0531fdffb22204e0ec5ed84a",
                "md5ext": "cd21514d0531fdffb22204e0ec5ed84a.svg",
                "rotationCenterX": 240, "rotationCenterY": 180,
            }],
            "sounds": [], "currentCostume": 0, "volume": 100, "tempo": 60,
            "videoTransparency": 50, "videoState": "on",
            "textToSpeechLanguage": None, "layerOrder": 0,
        }],
        "monitors": [], "extensions": [], "meta": {"semver": "3.0.0"},
    }


def build_simplify_sample():
    """New simplification passes: folding, no-ops, inlining, propagation."""
    def blk(opcode, **kw):
        b = {"opcode": opcode, "next": None, "parent": None, "inputs": {},
             "fields": {}, "shadow": False, "topLevel": False}
        b.update(kw)
        return b

    def mut(code, warp="false", args="[]"):
        return {"tagName": "mutation", "children": [], "proccode": code,
                "argumentids": args, "argumentnames": args,
                "argumentdefaults": args, "warp": warp}

    V_NEVER = "sNever00000000000000"
    V_DOMI = "sDomi000000000000000"
    B_DEAD = "sDead000000000000000"
    B_LIVE = "sLive000000000000000"
    blocks = {}

    def add_script(hat_id, x, y):
        blocks[hat_id] = blk("event_whenflagclicked", topLevel=True, x=x, y=y)
        return hat_id

    def append(prev, bid, opcode, inputs=None, fields=None, mutation=None):
        blocks[prev]["next"] = bid
        blocks[bid] = blk(opcode, parent=prev, inputs=inputs or {},
                          fields=fields or {})
        if mutation is not None:
            blocks[bid]["mutation"] = mutation
        return bid

    # --- numeric folding ---
    add_script("foldHat000000000000", 0, 0)
    prev = "foldHat000000000000"
    fold_cases = [
        ("operator_divide", {"NUM1": [1, [4, "1"]], "NUM2": [1, [4, "0"]]}),
        ("operator_divide", {"NUM1": [1, [4, "-1"]], "NUM2": [1, [4, "0"]]}),
        ("operator_divide", {"NUM1": [1, [4, "0"]], "NUM2": [1, [4, "0"]]}),
        ("operator_mod", {"NUM1": [1, [4, "10"]], "NUM2": [1, [4, "3"]]}),
        ("operator_round", {"NUM": [1, [4, "-0.5"]]}),
        ("operator_mathop", {"NUM": [1, [4, "9"]]}),
    ]
    for i, (op, inputs) in enumerate(fold_cases):
        rep = f"foldRep{i:014d}"
        fields = {"OPERATOR": ["sqrt", None]} if op == "operator_mathop" else {}
        blocks[rep] = blk(op, parent=prev, inputs=inputs, fields=fields)
        say = f"foldSay{i:014d}"
        prev = append(prev, say, "looks_say",
                      inputs={"MESSAGE": [3, rep, [10, ""]]})
        blocks[rep]["parent"] = say

    # --- if/else without an else branch ---
    add_script("ifHat00000000000000", 0, 400)
    blocks["ifCond000000000000"] = blk(
        "operator_equals", parent="ifBlock000000000000",
        inputs={"OPERAND1": [1, [4, "1"]], "OPERAND2": [1, [4, "1"]]})
    blocks["ifBlock000000000000"] = blk(
        "control_if_else", parent="ifHat00000000000000",
        inputs={"CONDITION": [2, "ifCond000000000000"],
                "SUBSTACK": [2, "ifBody0000000000000"]})
    blocks["ifHat00000000000000"]["next"] = "ifBlock000000000000"
    blocks["ifBody0000000000000"] = blk(
        "motion_movesteps", parent="ifBlock000000000000",
        inputs={"STEPS": [1, [4, "1"]]})

    # --- no-op custom block ---
    blocks["noopDef000000000000"] = blk(
        "procedures_definition", topLevel=True, x=300, y=0,
        next="noopStop00000000000",
        inputs={"custom_block": [1, "noopProto0000000000"]})
    blocks["noopProto0000000000"] = blk(
        "procedures_prototype", parent="noopDef000000000000", shadow=True,
        mutation=mut("noop"))
    blocks["noopStop00000000000"] = blk(
        "control_stop", parent="noopDef000000000000",
        fields={"STOP_OPTION": ["this script", None]},
        mutation={"tagName": "mutation", "children": [], "hasnext": "false"})
    add_script("callHat0000000000000", 300, 300)
    prev = append("callHat0000000000000", "noopCall0000000000",
                  "procedures_call", mutation=mut("noop"))
    append(prev, "callTurn00000000000", "motion_turnright",
           inputs={"DEGREES": [1, [4, "15"]]})

    # --- single-call inlining (non-warp only) ---
    blocks["oneDef0000000000000"] = blk(
        "procedures_definition", topLevel=True, x=600, y=0,
        next="oneBody00000000000",
        inputs={"custom_block": [1, "oneProto00000000000"]})
    blocks["oneProto00000000000"] = blk(
        "procedures_prototype", parent="oneDef0000000000000", shadow=True,
        mutation=mut("one"))
    blocks["oneBody00000000000"] = blk(
        "motion_movesteps", parent="oneDef0000000000000",
        inputs={"STEPS": [1, [4, "2"]]})
    add_script("oneHat0000000000000", 600, 300)
    prev = append("oneHat0000000000000", "oneCall00000000000",
                  "procedures_call", mutation=mut("one"))
    append(prev, "oneTurn00000000000", "motion_turnleft",
           inputs={"DEGREES": [1, [4, "5"]]})
    blocks["warpDef000000000000"] = blk(
        "procedures_definition", topLevel=True, x=900, y=0,
        next="warpBody00000000000",
        inputs={"custom_block": [1, "warpProto0000000000"]})
    blocks["warpProto0000000000"] = blk(
        "procedures_prototype", parent="warpDef000000000000", shadow=True,
        mutation=mut("warpone", warp="true"))
    blocks["warpBody00000000000"] = blk(
        "motion_movesteps", parent="warpDef000000000000",
        inputs={"STEPS": [1, [4, "3"]]})
    add_script("warpHat0000000000000", 900, 300)
    append("warpHat0000000000000", "warpCall0000000000",
           "procedures_call", mutation=mut("warpone"))

    # --- no-op broadcast receiver and sender ---
    blocks["deadRecvHat000000000"] = blk(
        "event_whenbroadcastreceived", topLevel=True, x=1200, y=0,
        fields={"BROADCAST_OPTION": ["deadMsg", B_DEAD]})
    add_script("sendHat000000000000", 1200, 300)
    prev = append("sendHat000000000000", "deadSend0000000000",
                  "event_broadcast",
                  inputs={"BROADCAST_INPUT": [1, [11, "deadMsg", B_DEAD]]})
    append(prev, "liveSend0000000000", "event_broadcast",
           inputs={"BROADCAST_INPUT": [1, [11, "liveMsg", B_LIVE]]})
    blocks["liveRecvHat000000000"] = blk(
        "event_whenbroadcastreceived", topLevel=True, x=1200, y=500,
        next="liveBody00000000000",
        fields={"BROADCAST_OPTION": ["liveMsg", B_LIVE]})
    blocks["liveBody00000000000"] = blk(
        "motion_movesteps", parent="liveRecvHat000000000",
        inputs={"STEPS": [1, [4, "4"]]})

    # --- constant propagation ---
    add_script("constHat000000000000", 1500, 0)
    prev = "constHat000000000000"
    for i in range(2):
        say = f"neverSay{i:013d}"
        prev = append(prev, say, "looks_say", inputs={
            "MESSAGE": [3, [12, "never", V_NEVER], [10, ""]]})
    add_script("domiHat1000000000000", 1500, 300)
    prev = append("domiHat1000000000000", "domiSet00000000000",
                  "data_setvariableto", inputs={"VALUE": [1, [4, "7"]]},
                  fields={"VARIABLE": ["domi", V_DOMI]})
    append(prev, "domiSay10000000000", "looks_say", inputs={
        "MESSAGE": [3, [12, "domi", V_DOMI], [10, ""]]})
    add_script("domiHat2000000000000", 1500, 600)
    append("domiHat2000000000000", "domiSay20000000000", "looks_say", inputs={
        "MESSAGE": [3, [12, "domi", V_DOMI], [10, ""]]})

    return {
        "targets": [{
            "isStage": True, "name": "Stage",
            "variables": {V_NEVER: ["never", "K"], V_DOMI: ["domi", 5]},
            "lists": {}, "broadcasts": {B_DEAD: "deadMsg", B_LIVE: "liveMsg"},
            "blocks": blocks, "comments": {},
            "costumes": [{
                "name": "backdrop1", "dataFormat": "svg",
                "assetId": "cd21514d0531fdffb22204e0ec5ed84a",
                "md5ext": "cd21514d0531fdffb22204e0ec5ed84a.svg",
                "rotationCenterX": 240, "rotationCenterY": 180,
            }],
            "sounds": [], "currentCostume": 0, "volume": 100, "tempo": 60,
            "videoTransparency": 50, "videoState": "on",
            "textToSpeechLanguage": None, "layerOrder": 0,
        }],
        "monitors": [], "extensions": [], "meta": {"semver": "3.0.0"},
    }


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
    c6 = Compressor(Options(remove_unreachable=False,
                            clear_initial_values=False,
                            extract_duplicates=False))
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
    # 構成: score + ☁cloudvar + local + ghost(モニター参照で保持) / mylist は
    # 非表示モニターだけで参照され、書き込み・表示もないため削除される。
    assert len(svars7) == 4, f"変数数が不正: {names7}"
    assert "mylist" not in lnames7, f"非表示モニターだけのリストが残っている: {lnames7}"
    assert len(slists7) == 0, f"リスト数が不正: {lnames7}"
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
    st7b["blocks"]["staleHat00000000000"] = {
        "opcode": "event_whenflagclicked", "next": "staleRef00000000000",
        "parent": None, "inputs": {}, "fields": {}, "shadow": False,
        "topLevel": True, "x": 400, "y": 400,
    }
    st7b["blocks"]["staleRef00000000000"] = {
        "opcode": "data_setvariableto", "next": None,
        "parent": "staleHat00000000000",
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
    assert len(slists7b) == 1, \
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

    # ---------- 8) 新機能: 未表示ストア・初期値・到達不能・重複・隠れ既定値 ----------
    p10 = json.loads(json.dumps(build_feature_sample()))
    c10 = Compressor(Options())
    q10 = c10.run(p10)
    sv10, sl10, sb10 = flatten(q10)
    stage10, dup10 = q10["targets"][0], q10["targets"][1]
    st10 = c10.stats

    V10 = {
        "keepRead": "vKeepRead0000000000000",
        "hiddenOnly": "vHiddenOnly00000000000",
        "visibleOnly": "vVisibleOnly0000000000",
        "writeOnly": "vWriteOnly000000000000",
        "initVar": "vInitVar00000000000000",
        "selfVar": "vSelfVar00000000000000",
        "readFirst": "vReadFirst000000000000",
        "sensedVar": "vSensedVar000000000000",
        "looseVar": "vLooseVar0000000000000",
        "orphanVar": "vOrphanVar000000000000",
    }
    L10 = {
        "hiddenListOnly": "lHiddenOnly00000000000",
        "visibleListOnly": "lVisibleOnly0000000000",
        "readList": "lReadList0000000000000",
        "initList": "lInitList0000000000000",
        "appendList": "lAppendList00000000000",
        "deleteOnlyList": "lDeleteOnly00000000000",
        "readOnlyList": "lReadOnly000000000000",
    }
    B10 = {"usedMsg": "bUsedMsg00000000000000",
           "unusedMsg": "bUnusedMsg000000000000"}

    def vinit(key):
        vid = c10.var_map[V10[key]][0]
        assert vid in sv10, f"変数 {key} が誤って削除された"
        return sv10[vid][1]

    def linit(key):
        lid = c10.list_map[L10[key]][0]
        assert lid in sl10, f"リスト {key} が誤って削除された"
        return sl10[lid][1]

    # 非表示モニターだけのストアは削除、表示モニター・読み取りは保持。
    for key in ("hiddenOnly", "looseVar", "orphanVar"):
        assert c10.var_map[V10[key]][0] not in sv10, f"未表示変数 {key} が残存"
    assert c10.list_map[L10["hiddenListOnly"]][0] not in sl10, \
        "非表示モニターだけのリストが残存"
    # 読み取り専用変数はリテラルへ畳み込まれ、ストア自体も削除される。
    assert c10.var_map[V10["keepRead"]][0] not in sv10, \
        "読み取り専用変数がリテラルへ畳み込まれていない"
    assert st10["const_vars_inlined"] >= 1
    assert vinit("visibleOnly") == 12, "表示中変数が削除/変更された"
    assert linit("visibleListOnly") == [2], "表示中リストが削除/変更された"

    # 初期化済みの変数・リストは初期値を空白化。読み取りが先なら保持。
    assert vinit("writeOnly") == "", \
        "書き込み専用変数の初期値が空白化されていない"
    assert vinit("initVar") == "", \
        "使用前に初期化される変数の初期値が空白化されていない"
    assert vinit("selfVar") == 5, \
        "自己参照 change の初期値が誤って空白化された"
    assert vinit("readFirst") == 6, \
        "読み取りが先の変数の初期値が誤って空白化された"
    assert vinit("sensedVar") == 7, \
        "sensing_of 参照変数の初期値が誤って空白化された"
    assert linit("readList") == ["r"], "読み取り専用リストの初期値が変更された"
    assert linit("initList") == [], \
        "delete all で初期化されるリストの初期値が空白化されていない"
    assert linit("appendList") == ["y"], \
        "add to list のリスト初期値が誤って空白化された"
    assert linit("deleteOnlyList") == [], \
        "delete all のみのリスト初期値が空白化されていない"
    assert linit("readOnlyList") == ["q"], \
        "読み取り専用リストの初期値が誤って空白化された"
    assert st10["vars_initialized"] >= 2 and st10["lists_initialized"] >= 2

    # 放送: 送信されるメッセージとレシーバーだけが残る。
    assert c10.bc_map[B10["usedMsg"]][0] in sb10
    assert all(v[0] != "unusedMsg" for v in sb10.values()), \
        "未使用メッセージ定義が残存"
    assert any(b.get("opcode") == "event_broadcast"
               for b in stage10["blocks"].values() if isinstance(b, dict))
    recv_fields = [b.get("fields", {}).get("BROADCAST_OPTION", [None])[0]
                   for b in stage10["blocks"].values()
                   if isinstance(b, dict)
                   and b.get("opcode") == "event_whenbroadcastreceived"]
    assert recv_fields == [c10.bc_map[B10["usedMsg"]][1]], \
        f"未使用メッセージのレシーバーが残存: {recv_fields}"

    # 到達不能ブロック・コメント・未呼び出し定義の削除。
    ops10 = [b.get("opcode") for b in stage10["blocks"].values()
             if isinstance(b, dict)]
    codes10 = [b.get("mutation", {}).get("proccode")
               for b in stage10["blocks"].values()
               if isinstance(b, dict)
               and b.get("opcode") in ("procedures_definition",
                                      "procedures_prototype")]
    assert "dead" not in codes10, "呼び出されない定義が残存"
    assert ops10.count("event_whenbroadcastreceived") == 1
    assert stage10.get("comments") and len(stage10["comments"]) == 2, \
        f"到達可能/ワークスペースコメントが削除された: {stage10.get('comments')}"
    kept_comment = next(c for c in stage10["comments"].values()
                        if c.get("text") == "kept")
    assert kept_comment["blockId"] in stage10["blocks"]
    assert any(c.get("text") == "free note" and c.get("blockId") is None
               for c in stage10["comments"].values()), \
        "ワークスペースコメントが削除された"
    assert st10["unreachable_blocks_removed"] >= 7
    assert st10["unreachable_comments_removed"] >= 1
    assert st10["procs_removed"] >= 1 and st10["broadcasts_removed"] == 1

    # 演算ブロックに覆われた既定値の削除。
    gotoxy10 = next(b for b in stage10["blocks"].values()
                    if isinstance(b, dict) and b.get("opcode") == "motion_gotoxy")
    assert gotoxy10["inputs"]["X"][0] == 2 and len(gotoxy10["inputs"]["X"]) == 2, \
        f"隠れ既定値が削除されていない: {gotoxy10['inputs']['X']}"
    assert st10["obscured_shadows_removed"] >= 1

    # 連続する同一コードは定義化ではなく repeat にまとめる。
    dup_ops10 = [b.get("opcode") for b in dup10["blocks"].values()
                 if isinstance(b, dict)]
    assert st10["loops_created"] >= 2, \
        f"連続重複がループ化されていない: {st10['loops_created']}"
    assert st10["loop_blocks_saved"] >= 18, \
        f"ループ化でブロックが減っていない: {st10['loop_blocks_saved']}"
    assert dup_ops10.count("control_repeat") == 2
    assert len(dup10["blocks"]) < 26, "ループ化でブロック数が減っていない"

    # 非表示モニターは削除され、表示中モニターだけが残る。
    mon_params10 = {(m.get("opcode"), tuple(sorted((m.get("params") or {}).items())))
                    for m in q10["monitors"]}
    assert ("data_variable",
            (("VARIABLE", c10.var_map[V10["visibleOnly"]][1]),)) in mon_params10
    assert ("data_listcontents",
            (("LIST", c10.list_map[L10["visibleListOnly"]][1]),)) in mon_params10
    assert not any("hiddenOnly" in str(m) or "hiddenListOnly" in str(m)
                   for m in q10["monitors"]), "非表示モニターが残存"

    errs10 = validate_project(q10)
    assert not errs10, errs10
    print(f"[OK] 新機能一式（未表示削除・初期値 {st10['vars_initialized']}変数/"
          f"{st10['lists_initialized']}リスト・到達不能 {st10['unreachable_blocks_removed']}"
          f"ブロック・重複 {st10['duplicates_extracted']}組・隠れ既定値 "
          f"{st10['obscured_shadows_removed']}）")

    # warp（画面更新なし）定義内のコードは、同じ warp 定義へなら抽出できる。
    # 通常スクリプト側とは混ぜず、新定義も warp にする必要がある。
    p11 = build_warp_duplicate_sample()
    c11 = Compressor(Options(loop_duplicates=False))
    q11 = c11.run(p11)
    assert c11.stats["duplicates_extracted"] >= 1, \
        "warp 定義内の重複が抽出されていない"
    assert c11.stats["procs_removed"] == 0, "呼び出した定義が削除された"
    bs11 = q11["targets"][0]["blocks"]
    protos11 = [b for b in bs11.values()
                if isinstance(b, dict)
                and b.get("opcode") == "procedures_prototype"]
    new_protos11 = [p for p in protos11
                    if p["mutation"]["proccode"] != "warpy"]
    assert new_protos11, "抽出定義がない"
    assert sum(1 for p in protos11
               if p["mutation"]["proccode"] == "warpy") == 2, \
        "元の warp 定義が失われた"

    def owner_warp(block_id):
        cur = bs11[block_id].get("parent")
        seen = set()
        while isinstance(cur, str) and cur in bs11 and cur not in seen:
            seen.add(cur)
            blk = bs11[cur]
            if blk.get("opcode") == "procedures_definition":
                cb = (blk.get("inputs") or {}).get("custom_block")
                pid = cb[1] if isinstance(cb, list) and len(cb) > 1 else None
                proto = bs11.get(pid) or {}
                warp = (proto.get("mutation") or {}).get("warp")
                return str(warp) == "true"
            cur = blk.get("parent")
        return False

    for proto in new_protos11:
        code = proto["mutation"]["proccode"]
        calls = [bid for bid, b in bs11.items()
                 if isinstance(b, dict)
                 and b.get("opcode") == "procedures_call"
                 and b["mutation"]["proccode"] == code]
        assert calls, f"抽出定義 {code} の呼び出しがない"
        inside = {owner_warp(cid) for cid in calls}
        assert len(inside) == 1, f"{code} が warp/通常の両方から呼ばれている"
        assert (proto["mutation"]["warp"] == "true") == inside.pop(), \
            f"warp 由来の抽出定義が warp になっていない: {proto['mutation']}"
    assert any(p["mutation"]["warp"] == "true" for p in new_protos11), \
        "warp 由来の抽出定義がない"
    errs11 = validate_project(q11)
    assert not errs11, errs11
    print("[OK] warp定義内の重複はwarp定義へ抽出（画面更新タイミング保持）")

    # ---------- 8b) 引数付き定義内の重複抽出 ----------
    # 同じ定義内で同じ引数を使う重複は、引数を新定義へ渡して抽出できる。
    p12 = build_argument_duplicate_sample("same_def")
    c12 = Compressor(Options(compress_procs=False, loop_duplicates=False))
    q12 = c12.run(p12)
    bs12 = q12["targets"][0]["blocks"]
    st12 = c12.stats
    assert st12["duplicates_extracted"] == 1, \
        f"引数付き重複が抽出されていない: {st12}"
    protos12 = {b["mutation"]["proccode"]: b for b in bs12.values()
                if isinstance(b, dict)
                and b.get("opcode") == "procedures_prototype"}
    assert "proc %s %b" in protos12, f"元の定義が失われた: {list(protos12)}"
    dup12 = protos12.get("dup1 %s %b")
    assert dup12 is not None, f"引数付き抽出定義がない: {list(protos12)}"
    dmut = dup12["mutation"]
    assert json.loads(dmut["argumentnames"]) == ["x", "flag"], dmut
    assert json.loads(dmut["argumentdefaults"]) == ["", False], dmut
    dup_args = json.loads(dmut["argumentids"])
    assert len(dup_args) == 2 and len(set(dup_args)) == 2
    dup_calls = [(cid, b) for cid, b in bs12.items()
                 if isinstance(b, dict)
                 and b.get("opcode") == "procedures_call"
                 and b["mutation"]["proccode"] == "dup1 %s %b"]
    assert len(dup_calls) == 2, f"抽出箇所の呼び出し数が不正: {len(dup_calls)}"
    for call_id, call in dup_calls:
        call_args = json.loads(call["mutation"]["argumentids"])
        assert call_args == dup_args
        kinds = {}
        for aid in call_args:
            assert aid in call["inputs"], f"引数 {aid} の入力がない"
            ref = call["inputs"][aid]
            reporter = bs12.get(ref[1])
            assert isinstance(reporter, dict), ref
            assert reporter.get("parent") == call_id, \
                "呼び出し側の引数レポーターの親が不正"
            kinds[reporter["opcode"]] = ref
        assert set(kinds) == {"argument_reporter_string_number",
                              "argument_reporter_boolean"}, kinds
        text_ref = kinds["argument_reporter_string_number"]
        bool_ref = kinds["argument_reporter_boolean"]
        assert text_ref[0] == 3 and text_ref[2] == [10, ""], text_ref
        assert bool_ref[0] == 2 and len(bool_ref) == 2, bool_ref
        assert bs12[text_ref[1]]["fields"]["VALUE"][0] == "x"
        assert bs12[bool_ref[1]]["fields"]["VALUE"][0] == "flag"
    errs12 = validate_project(q12)
    assert not errs12, errs12

    # 引数付き定義内でも、重複コードが引数を使わないなら引数なしで抽出する。
    p13 = build_argument_duplicate_sample("no_args")
    c13 = Compressor(Options(compress_procs=False, loop_duplicates=False))
    q13 = c13.run(p13)
    assert c13.stats["duplicates_extracted"] == 1, \
        "引数未使用の重複が抽出されていない"
    protos13 = {b["mutation"]["proccode"]: b for b in q13["targets"][0]["blocks"].values()
                if isinstance(b, dict)
                and b.get("opcode") == "procedures_prototype"}
    assert "dup1" in protos13, f"引数なし抽出定義がない: {list(protos13)}"
    assert json.loads(protos13["dup1"]["mutation"]["argumentnames"]) == []
    assert json.loads(protos13["dup1"]["mutation"]["argumentids"]) == []
    assert not validate_project(q13)

    # 別々の定義にまたがる引数利用は、呼び出し元の文脈が異なるため抽出しない。
    # 定義に存在しない引数名のレポーターも同様に対象外。
    for mode13 in ("different_defs", "undeclared"):
        p14 = build_argument_duplicate_sample(mode13)
        c14 = Compressor(Options(compress_procs=False))
        q14 = c14.run(p14)
        assert c14.stats["duplicates_extracted"] == 0, \
            f"{mode13}: 安全でない重複抽出が行われた"
        errs14 = validate_project(q14)
        assert not errs14, errs14
    print("[OK] 引数付き重複の抽出（同一引数のみ・引数未使用も可・"
          "別定義/未宣言は対象外）")

    # レポーター（演算ブロック）はスタック列ではないので抽出対象にしない。
    # 同じ演算サブツリーが5回現れても、定義本体へ移すとスクリプトが
    # コンパイルできなくなる（レポーターが積み木扱いになる）。
    p15 = build_reporter_duplicate_sample()
    assert sum(1 for b in p15["targets"][0]["blocks"].values()
               if isinstance(b, dict) and b.get("opcode") == "operator_add") == 5
    c15 = Compressor(Options(compress_procs=False))
    q15 = c15.run(p15)
    bs15 = q15["targets"][0]["blocks"]
    assert c15.stats["duplicates_extracted"] == 0, \
        "レポーターが重複抽出の対象になった"
    assert not any(isinstance(b, dict)
                   and b.get("opcode") == "procedures_definition"
                   for b in bs15.values()), "レポーターから定義が作られた"
    stack_targets = set()
    for b in bs15.values():
        if not isinstance(b, dict):
            continue
        nxt = b.get("next")
        if isinstance(nxt, str):
            stack_targets.add(nxt)
        if b.get("opcode") == "procedures_definition" \
                and isinstance(nxt, str):
            stack_targets.add(nxt)
        for key, value in (b.get("inputs") or {}).items():
            if (key in ("SUBSTACK", "SUBSTACK2") and isinstance(value, list)
                    and len(value) > 1 and isinstance(value[1], str)):
                stack_targets.add(value[1])
    for bid in stack_targets:
        op = bs15[bid].get("opcode", "")
        assert not op.startswith(("operator_", "argument_reporter")), \
            f"レポーターがスタック位置に移動した: {bid} {op}"
        assert op not in ("data_variable", "data_listcontents",
                          "data_itemoflist", "data_itemnumoflist",
                          "data_lengthoflist", "data_listcontainsitem"), \
            f"データレポーターがスタック位置に移動した: {bid} {op}"
    errs15 = validate_project(q15)
    assert not errs15, errs15
    print("[OK] レポーターは抽出せず、スタック列だけを対象にする")

    # ---------- 8b-2) リテラル差分だけを持つ近似的な重複の抽出 ----------
    p17 = build_near_duplicate_sample("literals")
    c17 = Compressor(Options(compress_procs=False, loop_duplicates=False))
    q17 = c17.run(p17)
    bs17 = q17["targets"][0]["blocks"]
    st17 = c17.stats
    assert st17["near_duplicates_extracted"] == 1, \
        f"リテラル差分の重複が抽出されていない: {st17}"
    assert st17["near_blocks_saved"] >= 10, \
        f"近似重複でブロックが減っていない: {st17}"
    protos17 = {b["mutation"]["proccode"]: b for b in bs17.values()
                if isinstance(b, dict)
                and b.get("opcode") == "procedures_prototype"}
    code17 = "ndup1 %s %s"
    assert code17 in protos17, f"近似抽出定義がない: {list(protos17)}"
    mut17 = protos17[code17]["mutation"]
    assert json.loads(mut17["argumentnames"]) == ["p1", "p2"], mut17
    assert json.loads(mut17["argumentdefaults"]) == ["", ""], mut17
    dup_args17 = json.loads(mut17["argumentids"])
    assert len(dup_args17) == 2 and len(set(dup_args17)) == 2
    # 本体側は差分スロットだけが引数レポーターになっている。
    body_reporters = [b for b in bs17.values()
                      if isinstance(b, dict)
                      and b.get("opcode") == "argument_reporter_string_number"
                      and b.get("parent") not in
                      {cid for cid, cb in bs17.items()
                       if isinstance(cb, dict)
                       and cb.get("opcode") == "procedures_call"}]
    assert len(body_reporters) == 2, \
        f"本体の引数レポーター数が不正: {len(body_reporters)}"
    assert {b["fields"]["VALUE"][0] for b in body_reporters} == {"p1", "p2"}
    calls17 = [(cid, b) for cid, b in bs17.items()
               if isinstance(b, dict)
               and b.get("opcode") == "procedures_call"
               and b["mutation"]["proccode"] == code17]
    assert len(calls17) == 3, f"呼び出し数が不正: {len(calls17)}"
    passed = set()
    for cid, call in calls17:
        assert json.loads(call["mutation"]["argumentids"]) == dup_args17
        vals = []
        for aid in dup_args17:
            ref = call["inputs"][aid]
            # 差分はリテラルのまま渡す（レポーターブロックを作らない）。
            assert ref[0] == 1 and isinstance(ref[1], list), ref
            assert ref[1][0] == 4, ref
            vals.append(ref[1][1])
        passed.add(tuple(vals))
    assert passed == {("1", "8"), ("1", "9"), ("10", "8")}, passed
    errs17 = validate_project(q17)
    assert not errs17, errs17

    # 無効化すると同じ入力からは定義を作らない。
    c17b = Compressor(Options(near_duplicates=False, compress_procs=False,
                              loop_duplicates=False))
    q17b = c17b.run(build_near_duplicate_sample("literals"))
    assert c17b.stats["near_duplicates_extracted"] == 0
    assert not any(isinstance(b, dict)
                   and b.get("opcode") == "procedures_definition"
                   for b in q17b["targets"][0]["blocks"].values())

    # プルダウン（フィールド）が異なるものは、リテラル差分があっても共有しない。
    p18 = build_near_duplicate_sample("field")
    c18 = Compressor(Options(compress_procs=False, loop_duplicates=False))
    q18 = c18.run(p18)
    assert c18.stats["near_duplicates_extracted"] == 0, \
        "プルダウンが異なるブロックが近似重複として抽出された"
    assert not any(isinstance(b, dict)
                   and b.get("opcode") == "procedures_definition"
                   for b in q18["targets"][0]["blocks"].values())
    assert not validate_project(q18)
    print("[OK] リテラル差分のみ引数化して近似重複を抽出（フィールド差分は対象外）")


    # ---------- 8c) 折り畳み・不要定義/放送・1回呼び出し・定数伝播 ----------
    V_NEVER_16 = "sNever00000000000000"
    V_DOMI_16 = "sDomi000000000000000"
    B_LIVE_16 = "sLive000000000000000"
    p16 = build_simplify_sample()
    c16 = Compressor(Options(compress_procs=False, extract_duplicates=False,
                             loop_duplicates=False, strip_defaults=False))
    q16 = c16.run(p16)
    bs16 = q16["targets"][0]["blocks"]
    st16 = c16.stats

    # if/else（else なし）は if へ。
    assert st16["ifelse_converted"] == 1
    ops16 = [b.get("opcode") for b in bs16.values() if isinstance(b, dict)]
    assert "control_if_else" not in ops16 and ops16.count("control_if") == 1

    # JavaScript の数値意味論で畳み込む。NaN (0/0) は畳み込まない。
    msgs16 = [b["inputs"]["MESSAGE"][1] for b in bs16.values()
              if isinstance(b, dict) and b.get("opcode") == "looks_say"]
    for expected in ([4, "Infinity"], [4, "-Infinity"], [4, "1"],
                     [4, "-0"], [4, "3"]):
        assert expected in msgs16, f"畳み込み結果がない: {expected} / {msgs16}"
    assert st16["const_values_folded"] == 5, st16["const_values_folded"]
    assert ops16.count("operator_divide") == 1, "0/0 が畳み込まれた"

    # 何もしない定義とその呼び出しは削除。warp の 1 回呼び出しは残す。
    assert st16["noop_procs_removed"] == 1 and st16["noop_calls_removed"] == 1
    assert st16["procs_inlined"] == 1, st16["procs_inlined"]
    protos16 = {b["mutation"]["proccode"]: b for b in bs16.values()
                if isinstance(b, dict)
                and b.get("opcode") == "procedures_prototype"}
    assert set(protos16) == {"warpone"}, list(protos16)
    assert ops16.count("procedures_call") == 1
    assert ops16.count("procedures_definition") == 1
    # 非 warp 定義の本体は呼び出し位置へ移動している。
    assert any(b.get("opcode") == "motion_movesteps"
               and (b.get("inputs") or {}).get("STEPS") == [1, [4, "2"]]
               for b in bs16.values() if isinstance(b, dict))

    # 空のレシーバーと送信だけの放送は削除し、実体のある放送は残す。
    assert st16["noop_receivers_removed"] == 1
    assert st16["noop_broadcasts_removed"] == 1
    assert st16["noop_messages_removed"] == 1
    live_key16 = c16.bc_map[B_LIVE_16][0]
    assert set(q16["targets"][0]["broadcasts"].keys()) == {live_key16}
    assert ops16.count("event_whenbroadcastreceived") == 1
    assert ops16.count("event_broadcast") == 1
    recv16 = next(b for b in bs16.values()
                  if isinstance(b, dict)
                  and b.get("opcode") == "event_whenbroadcastreceived")
    assert recv16["fields"]["BROADCAST_OPTION"][1] == live_key16

    # 定数伝播: 書き込みのない never は全読み取りを置換してストアも削除。
    # domi は「7 を書いた後」の読みだけ置換し、書き込み前の読みは残す。
    assert st16["const_vars_inlined"] == 2, st16["const_vars_inlined"]
    assert st16["const_reads_inlined"] == 3, st16["const_reads_inlined"]
    vars16 = q16["targets"][0]["variables"]
    assert c16.var_map[V_NEVER_16][0] not in vars16
    assert c16.var_map[V_DOMI_16][0] in vars16
    domi_id = c16.var_map[V_DOMI_16][0]
    domi_refs = [v for b in bs16.values() if isinstance(b, dict)
                 for v in (b.get("inputs") or {}).values()
                 if isinstance(v, list)
                 for item in v[1:]
                 if isinstance(item, list) and len(item) > 2
                 and item[0] == 12 and item[2] == domi_id]
    assert len(domi_refs) == 1, f"書き込み前の読みが消えた: {domi_refs}"
    assert [4, "7"] in msgs16
    assert not validate_project(q16), validate_project(q16)
    print("[OK] 数値畳み込み/if簡約/不要定義・放送/1回呼び出し/定数伝播")

    # ---------- 9) 実ファイル: sb3compressor.sb3 ----------
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

# SB3 Compressor

A lossless compressor for Scratch / TurboWarp project files (`.sb3`).

SB3 Compressor shrinks the `project.json` inside an `.sb3` file without
changing how the project behaves:

- **ID shortening** — block IDs and the names of variables, lists, and
  broadcasts are renamed to short generated IDs (`V1`, `L2`, `B3`, ...).
- **Default stripping** — fields that the Scratch VM reconstructs
  automatically (e.g. `volume: 100`, `visible: true`, `shadow: false`,
  empty `inputs`/`fields`) are removed.
- **Minification** — the JSON is re-serialized with no extra whitespace,
  then repacked with all assets into a new `.sb3`.

Typical savings depend on the project, but JSON-heavy projects often shrink
substantially with zero visual or behavioral difference in the editor.

## Requirements

- Python 3.8 or later (standard library only)
- Tkinter (bundled with standard CPython) — GUI mode only

## Usage

### GUI

Run with no arguments:

```console
python sb3_compressor.py
```

Pick a `.sb3` (or a raw `project.json`) file, press **Start**, then save the
result when it finishes.

### CLI

```console
python sb3_compressor.py input.sb3 [output.sb3]
```

If the output path is omitted, `input_compressed.sb3` is written next to the
input.

Example output:

```text
[load] 読み込み中: myproject.sb3
[parse] JSON解析中…
...
--------------------------------------------------
元 project.json : 1,234.5 KB
圧縮後          : 456.7 KB  (圧縮率 63.0% 削減)
最終ファイル    : myproject_compressed.sb3 (1.1 MB)
内訳: ブロックID改名 8421 / 変数 12 / リスト 3 / 放送 5
      既定値削除 19032 / モニター更新 4
```

(Progress messages are currently shown in Japanese.)

## How it works

1. Read the `.sb3` zip and parse `project.json`.
2. Walk every target and collect variable / list / broadcast definitions.
3. Rename all block IDs by traversing each script from its top-level block,
   remapping `parent`/`next`/input references, monitor IDs, and comment
   anchors. Unreachable blocks are renamed too so they cannot collide with
   newly generated IDs.
4. Drop default-valued fields that the VM restores on load.
5. Serialize compactly and repack the zip (assets are stored verbatim).

The result loads normally in Scratch and TurboWarp. Note that compressed
projects are not meant to be round-tripped back to "pretty" names — original
IDs and names are not recoverable from the output file.

## Notes & caveats

- Cloud variables keep their `☁` prefix; only the name after the prefix is
  shortened.
- The optional *"sprite click → stage click"* option rewrites
  `event_whenthisspriteclicked` blocks into `event_whenstageclicked`. This
  changes behavior and is off by default.
- Always keep a backup of your original `.sb3`. The tool is careful, but
  this is a one-way transformation.

## License

Distributed under the [MIT License](LICENSE).

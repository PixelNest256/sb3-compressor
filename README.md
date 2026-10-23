# SB3 Compressor

A behavior-preserving compressor for Scratch / TurboWarp project files (`.sb3`).

SB3 Compressor shrinks the `project.json` inside an `.sb3` file while keeping
the project's runtime behavior the same:

- **Block ID shortening** — block IDs are replaced with short generated keys.
  Frequently referenced IDs get the shortest keys, and unreachable blocks are
  renamed too so they cannot collide with newly generated IDs.
- **Store renaming** — variable, list, and broadcast names are renamed to short
  generated IDs (`V1`, `L2`, `B3`, ...). Cloud variables keep their `☁` prefix.
- **Unused store removal** — variables and lists that no block or monitor reads
  are dropped (enabled by default).
- **Custom block compression** — `proccode` and argument names of custom blocks
  are shortened, with definitions, calls, prototypes, and argument reporters
  updated together.
- **Default stripping** — fields that the Scratch VM reconstructs automatically
  (e.g. `volume: 100`, `visible: true`, `shadow: false`, empty
  `inputs`/`fields`) are removed.
- **Minification** — the JSON is re-serialized without extra whitespace, then
  repacked with all assets into a new `.sb3`.

Typical savings depend on the project, but JSON-heavy projects often shrink by
20–60% with no visual or behavioral difference in the editor or player.

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
result when it finishes. The GUI exposes the individual options.

### CLI

```console
python sb3_compressor.py input.sb3 [output.sb3]
```

If the output path is omitted, `input_compressed.sb3` is written next to the
input. The CLI uses the default options listed below.

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

(Progress messages are shown in Japanese.)

## Options

| Option | Default | Description |
| --- | --- | --- |
| `strip_defaults` | on | Remove fields the VM restores on load. |
| `shorten_ids` | on | Rename block IDs and stores to short generated IDs. |
| `remove_unused` | on | Drop variables/lists that are never read. |
| `compress_procs` | on | Shorten custom block proccodes and argument names. |
| `freq_ids` | on | Give the most frequently referenced blocks the shortest IDs. |
| `click_to_stage` | off | Rewrite sprite-click hats into stage-click hats. **Changes behavior.** |

## How it works

1. Read the `.sb3` zip and parse `project.json`.
2. Walk every target and collect variable / list / broadcast definitions.
3. Scan block fields, inputs, and monitors to find which stores are actually
   used. Unused variables and lists are removed.
4. Shorten custom block proccodes and argument names, updating definitions,
   calls, prototypes, and argument reporters.
5. Assign short block IDs by reference frequency, then remap `parent`, `next`,
   input references, monitor IDs, and comment anchors.
6. Drop default-valued fields that the VM restores on load.
7. Serialize compactly and repack the zip (assets are stored verbatim).

## Compatibility

The compressor keeps two details that the Scratch VM's interpreter relies on:

- Top-level blocks keep an explicit `"parent": null`.
- Reachable blocks at the end of a stack keep an explicit `"next": null`.

`Blocks.getTopLevelScript()` and the interpreter's Promise-resolution path
compare these fields against `null`; a missing key (`undefined`) can cause a
crash or re-execute a Promise-returning block every frame. The compiler path
happens to tolerate the omission, so both compiler and interpreter modes are
covered by the test suite.

The output has been differentially tested against TurboWarp's `scratch-vm`
(v2.1.46) with the compiler enabled and disabled, running the original and
compressed project side by side in a deterministic 900-frame scenario. The
per-frame state, broadcasts, questions/answers, and text-to-speech requests
were identical.

Note that compressed projects are not meant to be round-tripped back to
"pretty" names — original IDs and names are not recoverable from the output
file.

## Testing

```console
python test_sb3_compressor.py
```

## Notes & caveats

- Cloud variables keep their `☁` prefix; only the name after the prefix is
  shortened.
- Unused store removal changes the variable/list palette in the editor. Script
  behavior is unaffected because those stores are never read.
- The optional *"sprite click → stage click"* option rewrites
  `event_whenthisspriteclicked` blocks into `event_whenstageclicked`. This
  changes behavior and is off by default.
- Always keep a backup of your original `.sb3`. The tool is careful, but this
  is a one-way transformation.

## License

Distributed under the [MIT License](LICENSE).

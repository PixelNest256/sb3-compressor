# SB3 Compressor

A lossless compressor for Scratch / TurboWarp project files (`.sb3`).

SB3 Compressor shrinks the `project.json` inside an `.sb3` file without
changing how the project behaves:

- **ID shortening** — block IDs and the names of variables, lists, and
  broadcasts are renamed to short generated IDs (`V1`, `L2`, `B3`, ...).
- **Store cleanup** — variables and lists that are never displayed, written,
  or read are removed. Hidden monitors alone do not keep a store alive.
- **Initial-value cleanup** — saved initial values are blanked when every
  script overwrites the store before reading it. Self-referential updates and
  displayed/cloud stores are never touched.
- **Unreachable cleanup** — blocks, comments, uncalled custom-block
  definitions, and broadcast messages that no script uses are removed.
  Free-floating workspace comments are kept as notes.
- **Hidden default removal** — when a reporter block covers an input slot,
  the editor default stored underneath it is dropped.
- **Duplicate extraction** — identical code sequences are moved into a new,
  uniquely named custom block when doing so reduces the block count and JSON
  size. There is no fixed minimum length, so short repeated snippets are
  shared too as long as they pay for the definition overhead; sequences that
  occur three or more times are collected into a single definition. When the
  repeated code uses arguments of the enclosing custom block, the new block
  takes those arguments and each caller passes the original argument values
  through.
- **Near-duplicate extraction** — single-block patterns that match except for
  literal inputs (numbers or text) are shared as well. The differing literals
  become arguments of the generated custom block, so every call keeps its own
  value. Dropdown fields are part of the block identity and are never turned
  into arguments.
- **Loop shortcuts** — consecutive identical block groups are replaced by a
  `repeat` loop when that removes at least two blocks and shrinks the JSON.
- **Single-use definition inlining** — a non-warp custom block that is called
  exactly once is moved to its call site and its definition is removed.
- **No-op removal** — custom-block definitions that do nothing (empty, or only
  `stop this script`) are deleted together with their calls, and broadcast
  receivers that do nothing are deleted together with sends that no remaining
  receiver can act on.
- **Constant folding** — arithmetic reporter trees made only of numeric
  literals are replaced by their result using JavaScript number semantics
  (`1/0` → `Infinity`, `-1/0` → `-Infinity`; `0/0` is left alone, and
  transcendental functions are not folded).
- **Constant propagation** — reads of variables that are never written, or
  whose every write stores the same literal, are replaced by that value when
  the serialized JSON becomes smaller.
- **Argument ID shortening** — custom-block argument IDs are renamed to short
  generated IDs. Calls and prototypes repeat those IDs in their `mutation` and
  as input keys, so this is one of the larger savings.
- **Mutation cleanup** — legacy `tagName`/`children` keys left over from
  Scratch 2 conversions are dropped when `children` is empty.
- **Hidden monitor pruning** — a monitor that is hidden and that no
  `show variable`/`show list` block can reveal is removed.
- **Decimal rounding** — costume rotation centers with long fractional digits
  are rounded to four decimals (a sub-pixel change in metadata only).
- **`if-else` simplification** — an `if-else` block with no else branch is
  converted to the smaller `if` block.
- **Default stripping** — fields that the Scratch VM reconstructs
  automatically (e.g. `volume: 100`, `visible: true`, `shadow: false`,
  empty `inputs`/`fields`) are removed.
- **Minification** — the JSON is re-serialized with no extra whitespace,
  then repacked with all assets into a new `.sb3`.

Two optional passes go beyond behavior preservation and are off by default:

- **Comment removal** (`strip_comments`) — deletes every workspace comment.
  Comments never execute, but their text is lost.
- **Workspace re-flow** (`compact_workspace`) — re-lays out top-level scripts
  onto a compact grid. Columns and the top-to-bottom order are preserved; only
  the editor layout changes.

Typical savings depend on the project, but JSON-heavy projects often shrink
substantially with zero visual or behavioral difference in the editor.

There are two ways to run it: the Python tool below, or the browser version in
`docs/`, which needs no install and can be published with GitHub Pages.

## Requirements

- Python 3.8 or later (standard library only)
- Tkinter (bundled with standard CPython) — GUI mode only

The browser version needs only a current browser; Python is not involved.

## Usage

### GUI

Run with no arguments:

```console
python sb3_compressor.py
```

Pick a `.sb3` (or a raw `project.json`) file, press **Start Compression**, then
save the result when it finishes. The GUI exposes the main options.

### CLI

```console
python sb3_compressor.py input.sb3 [output.sb3]
```

If the output path is omitted, `input_compressed.sb3` is written next to the
input. The CLI uses the default options listed below.

Example output:

```text
[load] Loading: myproject.sb3
[parse] Parsing JSON...
...
--------------------------------------------------------------
Original project.json : 1,234.5 KB
Compressed            : 456.7 KB  (63.0% smaller)
Output file           : myproject_compressed.sb3 (1.1 MB)
Details: blocks renamed 8421 / variables 12 / lists 3 / broadcasts 5
         defaults removed 19032 / unused vars/lists removed 149 / custom blocks shortened 4 / monitors updated 4
         unreachable blocks 771 / comments 5 / broadcasts 1 / obscured defaults 1250
         initial values cleared 7 / duplicate groups 1 (14 blocks saved) / near-duplicates 1 (8 blocks saved)
         loops 1 (6 blocks saved) / defs inlined 1 / folded values 5 / constant vars 2 (3 reads)
         no-op defs 1 / no-op messages 1 / if-else simplified 0
```

Progress and summary messages are written in English.

### Browser version (no install)

`docs/` contains a self-contained browser build of the same compressor. It has
no build step and no server-side code: `index.html`, `styles.css`, `app.js`,
`worker.js`, `compressor.js`, and a vendored copy of JSZip.

1. Open the page.
2. Drop an `.sb3` file (or a raw `project.json`) onto it, or choose one.
3. Wait for the readout, then press **Download**.

Compression runs in a Web Worker, and every option from the table below is
available on the page. The file never leaves the tab; there is no upload and no
Python/Pyodide in the browser. Cancelling a run terminates the worker; the
in-tab fallback cannot be interrupted once compression starts.

Serving the page over HTTP is recommended, because the Web Worker keeps the
interface responsive while a project is compressed. Opening `docs/index.html`
directly from disk also works: browsers block workers on `file://` URLs, so the
page detects that and compresses in the main tab instead. The tab will pause
until the readout appears.

The interface follows the operating system's light or dark preference by
default. The **Light / Dark** switch in the header overrides it, and the choice
is remembered in `localStorage`.

The English page lives at `docs/index.html` and the Japanese page at
`docs/ja/index.html` (served at `/ja/`). The header switch moves between them;
both use the same stylesheet and compressor engine.

To preview locally:

```console
python -m http.server 8000 --directory docs
```

Then open <http://localhost:8000/>.

To publish with GitHub Pages, push the repository and set
**Settings → Pages → Deploy from a branch → `main` / `docs`**. The page is then
served at `https://<user>.github.io/sb3-compressor/`. `docs/.nojekyll` keeps
Jekyll from touching the directory.

The browser engine is a direct port of `sb3_compressor.py`. On the optional
`test.sb3` fixture it produces the same `project.json` size and the same
statistics as the Python build; the two outputs are deep-equal apart from JSON
key order. Zip entries other than `project.json` are copied verbatim, so
costumes and sounds are unchanged.

### Tests

```console
python test_sb3_compressor.py
python test_strict_sb3_compressor.py
```

The strict suite adds structural validation, determinism checks, and a seeded
fuzz corpus. It also uses `test.sb3` and `repeat.sb3` when those optional
project fixtures are present.

## Options

All options are on by default except `click_to_stage`.

| Option | Default | Description |
| --- | --- | --- |
| `strip_defaults` | on | Remove fields the VM restores on load. |
| `shorten_ids` | on | Rename block IDs and stores to short generated IDs. |
| `remove_unused` | on | Drop variables/lists that are never referenced. |
| `compress_procs` | on | Shorten custom block proccodes and argument names. |
| `freq_ids` | on | Give the most frequently referenced blocks the shortest IDs. |
| `drop_obscured_shadows` | on | Drop input defaults hidden under covering reporters. |
| `remove_unreachable` | on | Remove unreachable blocks, comments, definitions, and messages. |
| `clear_initial_values` | on | Blank provably overwritten variable/list initial values. |
| `extract_duplicates` | on | Extract repeated block sequences into custom blocks. |
| `near_duplicates` | on | Share blocks that differ only in literal inputs. |
| `simplify_if_else` | on | Convert an `if-else` without an else branch to `if`. |
| `remove_noops` | on | Remove empty definitions, calls, and dead broadcast receivers. |
| `inline_single_call` | on | Inline non-warp definitions called exactly once. |
| `fold_constants` | on | Fold arithmetic on numeric literals. |
| `loop_duplicates` | on | Replace adjacent identical groups with `repeat` loops. |
| `propagate_constants` | on | Replace reads of constant stores with their value. |
| `click_to_stage` | off | Rewrite sprite-click hats into stage-click hats. **Changes behavior.** |
| `strip_comments` | off | Delete every workspace comment. **Their text is lost.** |
| `compact_workspace` | off | Re-flow top-level scripts onto a compact grid. |

## How it works

1. Read the `.sb3` zip and parse `project.json`.
2. Remove input defaults hidden under covering reporter blocks, then prune
   unreachable scripts, uncalled definitions, unused broadcast receivers and
   messages, and comments anchored to removed blocks.
3. Walk every target and collect variable / list / broadcast definitions,
   then analyze reads, writes, display state, monitors, and initial values.
4. Remove dead stores, blank provably overwritten initial values, then run the
   structural simplification passes: `if-else` → `if`, no-op definition and
   message removal, single-call inlining, constant propagation, numeric
   folding, and consecutive-duplicate loopization.
5. Rename all block IDs by traversing each script from its top-level block,
   remapping `parent`/`next`/input references, monitor IDs, and comment
   anchors.
6. Extract repeated block sequences into unique custom blocks when the result
   is smaller, share near-duplicate single blocks by passing their differing
   literals as arguments, then shorten custom-block names and arguments.
7. Drop default-valued fields that the VM restores on load.
8. Serialize compactly and repack the zip (assets are stored verbatim).

The result loads normally in Scratch and TurboWarp. Note that compressed
projects are not meant to be round-tripped back to "pretty" names — original
IDs and names are not recoverable from the output file.

## Compatibility

The compressor keeps two details that the Scratch VM's interpreter relies on:

- Top-level blocks keep an explicit `"parent": null`.
- Reachable blocks at the end of a stack keep an explicit `"next": null`.

`Blocks.getTopLevelScript()` and the interpreter's Promise-resolution path
compare these fields against `null`; a missing key (`undefined`) can cause a
crash or re-execute a Promise-returning block every frame. The compiler path
tolerates the omission, so both compiler and interpreter modes are covered by
the test suite.

The output has been differentially tested against TurboWarp's `scratch-vm`
with the compiler enabled and disabled, running the original and compressed
project side by side in a deterministic 900-frame scenario. Per-frame state,
broadcasts, questions/answers, and text-to-speech requests were identical.

## Notes & caveats

- Cloud variables keep their `☁` prefix; only the name after the prefix is
  shortened.
- A store that is only shown through a hidden monitor and has no reading or
  writing block is treated as dead. Free-floating workspace comments are kept.
- Initial values are cleared only when the analysis is sure the old value is
  never observed; visible monitors and cloud variables are excluded.
- Duplicate extraction keeps an extraction only when both the block count and
  serialized JSON shrink; candidates that would grow the JSON are skipped and
  the next-best candidate is tried. There is no fixed minimum sequence length,
  but very short repeats usually cost more in definition/call overhead than
  they save and are rejected by that check. Argument-using code is only
  extracted when every occurrence belongs to the same custom-block definition;
  those arguments become parameters of the generated block. Code from a "run
  without screen refresh" (warp) definition is only moved into another warp
  definition, preserving refresh timing.
- Near-duplicate extraction is limited to one stack block and its reporter
  subtree per candidate. Only literal input slots can become arguments; a
  difference in a dropdown field (for example the trigonometric function of
  `operator_mathop`) means the blocks are not merged, because Scratch has no
  way to evaluate a reporter in a field slot. The pass is also guarded by the
  same "blocks and JSON must both shrink" check as duplicate extraction.
- Numeric folding follows JavaScript arithmetic, because that is what the
  Scratch VM uses. Division by zero produces `Infinity`/`-Infinity`, while
  `NaN` results (`0/0`) and transcendental functions are left for the VM to
  evaluate.
- Loopization only merges copies that are adjacent in the same script, and it
  keeps the loop only when the serialized JSON actually shrinks.
- Single-call inlining never touches warp definitions, definitions with
  arguments, or bodies containing `stop this script`, and it never inlines
  into a warp caller.
- Constant propagation skips displayed, cloud, monitored, sensed, and
  extension-touched stores. A variable whose reading is only possible before
  its first write keeps its original value, because only dominated reads are
  replaced.
- The optional *"sprite click → stage click"* option rewrites
  `event_whenthisspriteclicked` blocks into `event_whenstageclicked`. This
  changes behavior and is off by default.
- Always keep a backup of your original `.sb3`. The tool is careful, but
  this is a one-way transformation.

## License

Distributed under the [MIT License](LICENSE).

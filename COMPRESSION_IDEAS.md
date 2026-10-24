# Compression ideas and measured effects

Notes for future work on `project.json` compression. Scratch applies upload
limits to the size of `project.json`, so the raw JSON size is the metric that
matters most; the `.sb3` size is reported too because it is what users see.

All numbers below were measured on `test.sb3` with the reference build of
`sb3_compressor.py`:

| | bytes |
| --- | --- |
| original `project.json` | 489,605 |
| compressed before this round of work | 238,956 |
| compressed after ideas 1, 2, 3, 7 | 217,837 (−8.8%) |

`raw` is the size of `project.json` after serialization; `sb3` is the change in
the compressed `.sb3` (DEFLATE). They differ a lot: repeated strings that
DEFLATE already collapses barely move the `.sb3` size even when they shrink the
raw JSON considerably.

## Implemented

| # | Idea | raw | sb3 | Option |
| --- | --- | --- | --- | --- |
| 1 | Argument ID shortening | −8.9 KB | −1.7 KB | `shorten_ids` |
| 2 | Legacy mutation key removal | −7.5 KB | −0.2 KB | `strip_defaults` |
| 3 | Hidden monitor pruning | −3.9 KB | −0.5 KB | `remove_unused` |
| 5 | Comment removal | −1.4 KB | −0.7 KB | `strip_comments` (off) |
| 6 | Workspace re-flow | −0.0 KB | −0.0 KB | `compact_workspace` (off) |
| 7 | Decimal rounding | −0.8 KB | −0.2 KB | `strip_defaults` |

### 1. Argument ID shortening

Custom-block argument IDs (`mutation.argumentids`, and the input keys of
`procedures_call`/`procedures_prototype`) were previously reserved but never
renamed. In `test.sb3` there are 38 distinct argument IDs, each 20 characters,
repeated across 208 mutations and 242 input keys: 9,440 characters in total.
They are now mapped to `encode_id` output (`A`, `B`, ...), which saves 8.9 KB of
raw JSON. The pass runs when `shorten_ids` is on, uses one project-wide map, and
rewrites `mutation.argumentids`, the `inputs` keys, and any `VALUE` field that
happens to hold an ID.

### 2. Legacy mutation key removal

Scratch 2 conversions leave `"tagName": "mutation"` and `"children": []` in
every procedure mutation (208 of them, plus 6 `control_stop`). They are only
dropped when `children` is empty, because non-empty `children` can still carry
old XML argument defaults. `control_stop` keeps `hasnext`, which the editor uses
to decide whether blocks can attach below a stop block.

### 3. Hidden monitor pruning

`test.sb3` carries 34 monitors that are all `visible: false` (3.9 KB). A monitor
entry can now be dropped when it is hidden **and** no
`data_showvariable`/`data_showlist` block references the store, because nothing
can ever draw it. Monitors that are visible, or that a show block can reveal, are
kept exactly as before. Gated by `remove_unused`.

### 5. Comment removal (opt-in)

`strip_comments` deletes every workspace comment (and the `comment` field on
blocks). Comments never execute, but their text is user content, so this is off
by default. Measured at 1.4 KB raw on `test.sb3`; tutorial-style projects can
save far more.

### 6. Workspace re-flow (opt-in)

`compact_workspace` renumbers the coordinates of top-level blocks: the distinct
x columns and the top-to-bottom order inside each column are preserved, spacing
is recomputed from the size of each script, and anchored comments follow their
block. Dropping coordinates entirely would save about 1.0 KB raw, but every
script would pile up at the origin in the editor, so that variant was rejected.
The conservative re-flow measured only −2 bytes on `test.sb3` (its coordinates
were already compact), which is why it stays off by default: it is a tidiness
option, not a size option.

### 7. Decimal rounding

Costume `rotationCenterX`/`rotationCenterY` sometimes carry 15–17 significant
digits from external tools (`96.99250489598867`). Values are rounded to four
decimals when the fractional part is longer; integers and `bitmapResolution`
are untouched. The visual difference is well below one pixel.

## Deferred (higher risk or lower value)

| # | Idea | estimate | Why deferred |
| --- | --- | --- | --- |
| 4 | Asset ID compaction | −2.4 KB raw, −2.2 KB sb3 | Requires renaming zip entries and `assetId`s, breaking the MD5 convention. |
| 9 | Typed identity/constant-condition folding | project dependent | Needs a type guard and an impure-reporter blacklist. |
| 10 | `[name, null]` field trimming, unused `extensions`, `hasnext:"false"` | −0.75 KB raw for the field case | Needs verification of how the VM casts one-element field arrays. |

### 4. Asset ID compaction

`assetId` is a 32-character MD5 for each of the 118 assets (3.8 KB in
`test.sb3`). Renaming the assets to short IDs (and updating `assetId`/`md5ext`
and the zip entry names) is allowed by the project rules — asset *bytes* are
untouched — and it is the largest `.sb3` win of the whole list because hashes
are high-entropy and compress badly. It is deferred because the name no longer
matches the content hash, which may confuse scratch.mit.edu or third-party
tools. It would ship as an off-by-default option with a warning.

### 9. Typed identity and constant-condition folding

Extend the existing folding with:

- `if <true> { ... }` → the body; `if <false> { }` → nothing.
- `x + 0`, `x - 0`, `x * 1`, `x / 1`, `join(x, "")` → `x`, but only when `x` is
  provably numeric/string (literals, `x position`, `size`, `timer`,
  `length of`, `mathop` results).
- Stack no-ops such as `change x by 0`, `change [variable] by 0`,
  `change [effect] by 0` (they never yield).

`operator_random` must be treated as impure (it advances the RNG), and `wait 0`
must not be touched because it yields a frame. This needs a small type/purity
analysis plus tests before it ships.

### 10. Small wins

- 150 menu fields carry a trailing `null` ID (`["name", null]`). Dropping it
  would save ~0.75 KB raw, but the VM's handling of one-element field arrays
  has to be verified first.
- `extensions` entries that no block uses can be removed (both were used in
  `test.sb3`).
- `control_stop` with `hasnext: "false"` could drop the key (false is the
  default). Only 6 occurrences here, so it is not worth the risk yet.
- `layerOrder` renumbering to `0..n-1` is safe in principle but measured *worse*
  here (digits got longer), so it should only trigger when the stored values are
  sparse or large.

## Measured and rejected

| Idea | Measurement | Reason |
| --- | --- | --- |
| Canonical key order for better DEFLATE | −0.2 KB sb3, ±0 raw | Small gain; would also make JS/Python output byte-comparable, so it may still be worth doing one day. |
| Dropping all workspace coordinates | −1.0 KB raw | Every script lands at the origin in the editor. |
| Dropping `parent: null` / `next: null` | large | The VM's `getTopLevelScript()` and the interpreter depend on them; documented in the README. |
| Dropping `parent` on non-top blocks | moderate | Needed by the editor and script highlighting. |
| Merging identical sprites | large | Clone limits and `sensing` would change. |
| Re-encoding assets | large | Out of scope: assets are never modified. |
| Cross-target code extraction | moderate | Impossible without clones. |

## Verification checklist for new passes

1. Structural validator (`validate_project`) on synthetic fixtures and on
   `test.sb3` / `repeat.sb3`.
2. Determinism: compressing twice must produce identical bytes.
3. Seeded fuzz corpus in `test_strict_sb3_compressor.py`.
4. Differential playback against TurboWarp's `scratch-vm` (compiler on and off).
5. Python ↔ JavaScript parity through the Node harness: identical
   `project.json` size, deep-equal JSON, identical statistics.
6. For VM-format assumptions (ideas 2, 10), add a targeted test that loads the
   output in the editor before trusting the change.

# Vendored libraries

`docs/media/vendor/` holds prebuilt browser bundles produced by
`build/media/`. Each is a plain IIFE script that assigns one global.

| File | Global | Source | License |
| --- | --- | --- | --- |
| `svgo.js` | `SVGO` | [SVGO](https://github.com/svg/svgo) 4.x (browser build) | MIT |
| `jpeg.js` | `JSQ_JPEG` | [@jsquash/jpeg](https://github.com/jamsinclair/jSquash) 1.x — MozJPEG | Apache-2.0 |
| `mozjpeg_enc.wasm` | — | MozJPEG (via @jsquash/jpeg) | Apache-2.0 / IJG |
| `oxipng.js` | `JSQ_OXIPNG` | [@jsquash/oxipng](https://github.com/jamsinclair/jSquash) 2.x — OxiPNG | Apache-2.0 |
| `oxipng_bg.wasm` | — | OxiPNG (via @jsquash/oxipng) | MIT |
| `mp3.js` | `WME` | [wasm-media-encoders](https://github.com/arseneyr/wasm-media-encoders) — LAME | MIT bundle; LAME is LGPL-2.1 |
| `mp3dec.js` | `WAD_MP3` | [mpg123-decoder](https://github.com/eshaz/wasm-audio-decoders) — mpg123 | MIT bundle; mpg123 is LGPL-2.1 |

Notes:

- The MozJPEG and OxiPNG bundles are derived from Google's Squoosh app and
  repackaged by jSquash.
- The MP3 encoder (LAME) and decoder (mpg123) are LGPL-2.1 libraries; the
  wrapper packages that bundle them are MIT. The library text is unmodified and
  only linked dynamically at runtime through WebAssembly, which keeps the LGPL
  terms satisfied for a web deployment.
- Each bundle is loaded only when its method is actually used, so a page that
  never converts audio or re-encodes images never downloads the audio codecs.

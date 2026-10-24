# Media compressor vendor build

Builds the browser libraries used by `docs/media/` into plain IIFE scripts and
copies their WASM binaries into `docs/media/vendor/`. The generated files are
committed, so this only needs to be run when the libraries are updated.

```console
cd build/media
npm install
node build.mjs
```

| Bundle | Library | License |
| --- | --- | --- |
| `jpeg.js` + `mozjpeg_enc.wasm` | [@jsquash/jpeg](https://github.com/jamsinclair/jSquash) (MozJPEG) | Apache-2.0 |
| `oxipng.js` + `oxipng_bg.wasm` | [@jsquash/oxipng](https://github.com/jamsinclair/jSquash) (OxiPNG) | Apache-2.0 |
| `mp3.js` | [wasm-media-encoders](https://github.com/arseneyr/wasm-media-encoders) (LAME) | MIT (bundles LGPL LAME) |
| `mp3dec.js` | [mpg123-decoder](https://github.com/eshaz/wasm-audio-decoders) (mpg123) | MIT |
| `svgo.js` | [SVGO](https://github.com/svg/svgo) | MIT |

`npm install` needs network access; nothing else does.

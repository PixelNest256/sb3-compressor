/* Vendor the browser libraries into docs/media/vendor as plain IIFE scripts.
 *
 *   cd build/media
 *   npm install
 *   node build.mjs
 *
 * Requires network access for `npm install`; nothing else. The generated files
 * are committed, so a normal checkout does not need to run this.
 */
import { build } from "esbuild";
import { mkdirSync, copyFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(here, "..", "..", "docs", "media", "vendor");
const nm = path.join(here, "node_modules");
mkdirSync(outDir, { recursive: true });

const common = {
  bundle: true,
  format: "iife",
  platform: "browser",
  target: ["es2020"],
  minify: true,
  legalComments: "none",
  define: { "import.meta.url": '"https://localhost/"' },
};

async function bundle(file, entry, globalName) {
  await build({
    ...common,
    entryPoints: [path.join(here, "src", entry)],
    outfile: path.join(outDir, file),
    globalName,
  });
  console.log(`  ${file.padEnd(14)} ${(statSync(path.join(outDir, file)).size / 1024).toFixed(1)} KB`);
}

const copies = [
  ["@jsquash/jpeg/codec/enc/mozjpeg_enc.wasm", "mozjpeg_enc.wasm"],
  ["@jsquash/oxipng/codec/pkg/squoosh_oxipng_bg.wasm", "oxipng_bg.wasm"],
];

console.log("bundling:");
await bundle("jpeg.js", "jpeg.mjs", "JSQ_JPEG");
await bundle("oxipng.js", "oxipng.mjs", "JSQ_OXIPNG");
await bundle("mp3.js", "mp3.mjs", "WME");
await bundle("mp3dec.js", "mp3dec.mjs", "WAD_MP3");
await bundle("svgo.js", "svgo.mjs", "SVGO");

console.log("wasm:");
for (const [src, dst] of copies) {
  copyFileSync(path.join(nm, src), path.join(outDir, dst));
  console.log(`  ${dst.padEnd(20)} ${(statSync(path.join(outDir, dst)).size / 1024).toFixed(1)} KB`);
}
console.log("done ->", outDir);

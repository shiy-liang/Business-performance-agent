import { build } from "esbuild";
import { copyFile, mkdir } from "node:fs/promises";
await build({
  entryPoints: ["chat-renderer.js", "chat-renderer.css"], bundle: true, minify: true,
  outdir: "vendor", format: "iife", globalName: "ChatRenderer",
  entryNames: "[name]",
  loader: { ".woff2": "file", ".woff": "file", ".ttf": "file" },
  assetNames: "fonts/[name]-[hash]", legalComments: "eof",
});
await mkdir("vendor/licenses", { recursive: true });
for (const [name, file] of [["marked", "LICENSE"], ["dompurify", "LICENSE"], ["katex", "LICENSE"]]) {
  await copyFile(`node_modules/${name}/${file}`, `vendor/licenses/${name}.txt`);
}

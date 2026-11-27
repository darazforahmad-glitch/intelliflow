// Bundles the Workbox service worker (sw/sw.ts) into public/sw.js.
import { build } from "esbuild";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

await build({
  entryPoints: ["sw/sw.ts"],
  bundle: true,
  minify: true,
  format: "iife",
  target: "es2020",
  outfile: "public/sw.js",
  logLevel: "warning",
  define: {
    "process.env.NODE_ENV": JSON.stringify(
      process.env.NODE_ENV === "development" ? "development" : "production",
    ),
    __API_URL__: JSON.stringify(apiUrl),
    __BUILD_ID__: JSON.stringify(Date.now().toString(36)),
  },
});
console.log("service worker built -> public/sw.js");

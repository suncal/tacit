// Renders transparent PNG overlays at 4K: the product frame per scene, and each lower-third callout from shots.json.
import { chromium } from "../tools/record/node_modules/playwright/index.mjs";
import { mkdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
const shots = JSON.parse(readFileSync("shots.json", "utf8")).shots;
const out = resolve("build/overlays"); mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
const base = "file://" + resolve("overlay.html");
async function shoot(params, file) {
  await page.goto(base + "?" + new URLSearchParams(params).toString());
  await page.evaluate(() => document.fonts.ready); await page.waitForTimeout(250);
  await page.screenshot({ path: resolve(out, file), omitBackground: true });
  console.log("overlay", file);
}
for (const s of shots) {
  if (!s.visual.startsWith("scene:")) continue;
  const f = s.frame || {};
  await shoot({ kind: "frame", title: f.title || "Tacit console", url: f.url || "127.0.0.1:4800", chapter: f.chapter || "" }, `${s.id}-frame.png`);
  for (const [i, c] of (s.callouts || []).entries()) await shoot({ kind: "callout", k: c.k || "live", t: c.t }, `${s.id}-c${i}.png`);
}
await browser.close();

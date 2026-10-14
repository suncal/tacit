// Records each motion card as a 1080p clip whose length equals its shot's narration length.
// Usage: node motion.mjs [card,card,...]   (default: every card:<id> in shots.json)
import { chromium } from "../tools/record/node_modules/playwright/index.mjs";
import { mkdirSync, renameSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { execSync } from "node:child_process";

const shots = JSON.parse(readFileSync("shots.json", "utf8")).shots;
const GAP = 0.30, XF = 0.5, TEMPO = parseFloat(process.env.TEMPO || "1.085");
const dur = (p) => parseFloat(execSync(`ffprobe -v error -show_entries format=duration -of csv=p=0 "${p}"`).toString());
const out = resolve("build/motion"); mkdirSync(out, { recursive: true });
const only = process.argv[2] ? new Set(process.argv[2].split(",")) : null;

const browser = await chromium.launch();
for (const s of shots) {
  if (!s.visual.startsWith("card:")) continue;
  const id = s.visual.split(":")[1];
  if (only && !only.has(id)) continue;
  const length = dur(`build/vo/${s.id}.mp3`) / TEMPO + GAP + XF + 0.3;
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1,
    recordVideo: { dir: out, size: { width: 1920, height: 1080 } } });
  const page = await ctx.newPage();
  await page.goto("file://" + resolve("motion.html") + `?card=${id}&dur=${(length - 0.8).toFixed(2)}`);
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(400);
  await page.evaluate(() => window.play());
  await page.waitForTimeout(length * 1000);
  const p = await page.video().path();
  await ctx.close();
  renameSync(p, resolve(out, `${id}.webm`));
  console.log("motion", id, length.toFixed(1) + "s");
}
await browser.close();

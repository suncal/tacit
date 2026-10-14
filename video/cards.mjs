// Renders every <section class="card"> in cards.html to build/cards/<id>.png at 1920x1080.
import { chromium } from "../tools/record/node_modules/playwright/index.mjs";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
const out = resolve("build/cards"); mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
await page.goto("file://" + resolve("cards.html"));
await page.evaluate(() => document.fonts.ready);
await new Promise((r) => setTimeout(r, 800));
const ids = await page.$$eval("section.card", (els) => els.map((e) => e.id));
for (const id of ids) {
  const el = await page.$("#" + id);
  await el.screenshot({ path: resolve(out, id + ".png") });
  console.log("card", id);
}
await browser.close();

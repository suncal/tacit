// Records console scenes for the TSM video: a 1080p screen recording of real pages on the live instance,
// plus 2x stills. Usage: node record.mjs <scene> [baseUrl]   scenes: shadow | all
import { chromium } from "playwright";
import { mkdirSync, readdirSync, renameSync } from "node:fs";
import { resolve } from "node:path";

const BASE = process.argv[3] || "http://127.0.0.1:4800";
const OUT = resolve(process.cwd(), "../../docs/tsm/captures");
const EMAIL = process.env.TACIT_DEMO_EMAIL || "demo@tacit.dev";
const PASSWORD = process.env.TACIT_DEMO_PASSWORD || "tacit-demo-2026";
mkdirSync(OUT, { recursive: true });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function login(page) {
  await page.goto(BASE + "/");
  await page.fill('input[type="email"]', EMAIL);
  await page.fill('input[type="password"]', PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((u) => !u.pathname.endsWith("/login"), { timeout: 10000 }).catch(() => {});
  await sleep(800);
}

// Slow, legible pointer travel so the viewer's eye follows.
async function glide(page, x, y, steps = 40) {
  await page.mouse.move(x, y, { steps });
}

async function sceneShadow(page) {
  await page.goto(BASE + "/shadow");
  await page.waitForSelector("text=Shadow");
  await sleep(2500);
  // read the three columns left to right
  await glide(page, 480, 270); await sleep(1400);
  await glide(page, 880, 270); await sleep(1800);
  await glide(page, 1270, 270); await sleep(1400);
  // the judge's reason
  await glide(page, 600, 322); await sleep(2600);
  // open the playbook
  const name = page.locator("text=Resend client invoice copy").first();
  const box = await name.boundingBox();
  if (box) { await glide(page, box.x + box.width / 2, box.y + box.height / 2); await sleep(700); await name.click(); }
  await page.waitForSelector("text=Wilson lower bound", { timeout: 10000 }).catch(() => {});
  await sleep(2200);
  await glide(page, 730, 250); await sleep(1600);            // the ladder, shadow stage lit
  await glide(page, 390, 420); await sleep(1400);            // trust 21%
  await page.mouse.wheel(0, 420); await sleep(2200);          // trigger + response + evidence
  await page.mouse.wheel(0, 500); await sleep(2600);
}

const scene = process.argv[2] || "shadow";
const browser = await chromium.launch();

// 1) video at 1080p
const vctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1,
  recordVideo: { dir: OUT, size: { width: 1920, height: 1080 } } });
const vpage = await vctx.newPage();
await login(vpage);
if (scene === "shadow" || scene === "all") await sceneShadow(vpage);
const videoPath = await vpage.video().path();
await vctx.close();
renameSync(videoPath, resolve(OUT, `${scene}.webm`));

// 2) stills at 2x for cutaways
const sctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
const spage = await sctx.newPage();
await login(spage);
for (const [name, path] of [["shadow", "/shadow"], ["playbook", "/playbooks"], ["overview", "/"]]) {
  await spage.goto(BASE + path); await sleep(1500);
  await spage.screenshot({ path: resolve(OUT, `${name}@2x.png`) });
}
await sctx.close();
await browser.close();
console.log("wrote", readdirSync(OUT).filter((f) => f.endsWith(".webm") || f.endsWith(".png")).join(", "));

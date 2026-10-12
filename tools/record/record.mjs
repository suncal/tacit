// Records console scenes for the TSM video: 1080p screen recordings of real pages on live instances, plus 2x stills.
// Usage: node record.mjs <scene,scene,...|all>
//   live instance (clean Slack org):   TACIT_LIVE_URL   default http://127.0.0.1:4800  (demo@tacit.dev)
//   seeded instance (Northwind org):   TACIT_SEED_URL   default http://127.0.0.1:4801  (demo@northwind.dev)
import { chromium } from "playwright";
import { mkdirSync, renameSync } from "node:fs";
import { resolve } from "node:path";

const LIVE = { base: process.env.TACIT_LIVE_URL || "http://127.0.0.1:4800", email: "demo@tacit.dev", password: process.env.TACIT_DEMO_PASSWORD || "tacit-demo-2026" };
const SEED = { base: process.env.TACIT_SEED_URL || "http://127.0.0.1:4801", email: "demo@northwind.dev", password: "tacit-demo" };
const CHANNEL = process.env.TACIT_DEMO_CHANNEL || "C0C8C6GBHL3";
const OUT = resolve(process.cwd(), "../../docs/tsm/captures");
mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function login(page, inst) {
  await page.goto(inst.base + "/");
  await page.fill('input[type="email"]', inst.email);
  await page.fill('input[type="password"]', inst.password);
  await page.click('button[type="submit"]');
  await page.waitForSelector("text=Overview", { timeout: 10000 }).catch(() => {});
  await sleep(800);
}
const glide = (page, x, y, steps = 40) => page.mouse.move(x, y, { steps });

const scenes = {
  // ---- live instance -------------------------------------------------------------------------------
  async shadow(page) {
    await page.goto(LIVE.base + "/shadow"); await page.waitForSelector("text=Shadow"); await sleep(2500);
    await glide(page, 480, 270); await sleep(1400);
    await glide(page, 880, 270); await sleep(1800);
    await glide(page, 1270, 270); await sleep(1400);
    await glide(page, 600, 322); await sleep(2600);
    const name = page.locator("text=Resend client invoice copy").first();
    const box = await name.boundingBox();
    if (box) { await glide(page, box.x + box.width / 2, box.y + box.height / 2); await sleep(700); await name.click(); }
    await page.waitForSelector("text=Wilson lower bound", { timeout: 10000 }).catch(() => {});
    await sleep(2200);
    await glide(page, 730, 250); await sleep(1600);
    await glide(page, 390, 420); await sleep(1400);
    await page.mouse.wheel(0, 420); await sleep(2200);
    await page.mouse.wheel(0, 500); await sleep(2600);
  },
  async overview(page) {
    await page.goto(LIVE.base + "/"); await page.waitForSelector("text=Overview"); await sleep(2500);
    await glide(page, 600, 300); await sleep(1500);
    await glide(page, 1100, 300); await sleep(1500);
    await page.mouse.wheel(0, 400); await sleep(2500);
    await page.mouse.wheel(0, 500); await sleep(2500);
  },
  async inbox(page) {
    // a real write, gated: the console asks Tacit to post, policy routes the write to the Inbox
    const r = await page.request.post(LIVE.base + "/api/v1/chat", { data: { text: `post in ${CHANNEL}: Reminder — invoices go out on the 1st. Ping here if a client needs a copy.` } });
    const run = (await r.json()).run;
    await sleep(1500);
    await page.goto(LIVE.base + "/inbox"); await page.waitForSelector("text=Approve", { timeout: 15000 }); await sleep(2500);
    await glide(page, 700, 330); await sleep(2200);                                  // read the preview
    const approve = page.locator("button:has-text('Approve')").first();
    const b = await approve.boundingBox();
    if (b) { await glide(page, b.x + b.width / 2, b.y + b.height / 2); await sleep(1800); await approve.click(); }
    await sleep(3500);                                                               // toast: approved and executed
    await page.goto(LIVE.base + "/runs/" + run.id); await page.waitForSelector("text=Undo", { timeout: 15000 }); await sleep(2500);
    await glide(page, 700, 420); await sleep(2000);                                  // the action, its result, the undo recorded
    page.once("dialog", (d) => d.accept());
    const undo = page.locator("button:has-text('Undo')").first();
    const u = await undo.boundingBox();
    if (u) { await glide(page, u.x + u.width / 2, u.y + u.height / 2); await sleep(1500); await undo.click(); }
    await sleep(4000);                                                               // reversed; tx undone
  },
  async evidence(page) {
    await page.goto(LIVE.base + "/compliance"); await sleep(2500);
    await glide(page, 700, 300); await sleep(1800);
    await page.mouse.wheel(0, 450); await sleep(2500);
    await page.mouse.wheel(0, 500); await sleep(2500);
    await page.goto(LIVE.base + "/audit"); await sleep(2500);
    await glide(page, 700, 320); await sleep(1500);
    await page.mouse.wheel(0, 400); await sleep(2500);
  },
  // ---- seeded instance (3 months of reviewer history) ------------------------------------------------
  async oversight(page) {
    await page.goto(SEED.base + "/oversight"); await sleep(2500);
    await glide(page, 700, 300); await sleep(1800);
    await glide(page, 1100, 300); await sleep(1500);
    await page.mouse.wheel(0, 450); await sleep(2500);
    await page.mouse.wheel(0, 500); await sleep(2500);
  },
  async oversightQuality(page) {
    await page.goto(SEED.base + "/oversight-quality"); await sleep(2500);
    await glide(page, 500, 300); await sleep(1800);                                  // index + band
    await page.mouse.wheel(0, 400); await sleep(2000);                               // components with weights
    await page.mouse.wheel(0, 450); await sleep(2500);                               // reviewers: jonas 1.3 s, 64% unread
    const jonas = page.locator("text=jonas").first();
    const jb = await jonas.boundingBox().catch(() => null);
    if (jb) { await glide(page, jb.x + 60, jb.y + jb.height / 2); await sleep(2500); }
    await page.mouse.wheel(0, 500); await sleep(2500);                               // findings
  },
};
const seeded = new Set(["oversight", "oversightQuality"]);

const want = (process.argv[2] || "all") === "all" ? Object.keys(scenes) : process.argv[2].split(",");
const browser = await chromium.launch();
for (const name of want) {
  const inst = seeded.has(name) ? SEED : LIVE;
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1,
    recordVideo: { dir: OUT, size: { width: 1920, height: 1080 } } });
  const page = await ctx.newPage();
  await login(page, inst);
  await scenes[name](page);
  const p = await page.video().path();
  await ctx.close();
  renameSync(p, resolve(OUT, `${name}.webm`));
  console.log("recorded", name);
}
// stills at 2x
for (const [inst, pages] of [[LIVE, ["", "shadow", "playbooks", "inbox", "runs", "compliance", "audit"]], [SEED, ["oversight", "oversight-quality", "report", "ledger"]]]) {
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await login(page, inst);
  for (const path of pages) {
    await page.goto(inst.base + "/" + path); await sleep(1500);
    await page.screenshot({ path: resolve(OUT, `${path || "overview"}@2x.png`) });
  }
  await ctx.close();
}
await browser.close();
console.log("done");

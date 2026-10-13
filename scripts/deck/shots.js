// Screenshots of the running web app for the deliverable-7 slides.
// Needs `python -m rmprep serve` on 127.0.0.1:8600 and puppeteer-core (NODE_PATH).
// Usage: node scripts/deck/shots.js <out dir> [persona id]
const fs = require("fs");
const path = require("path");
const puppeteer = require("puppeteer-core");

const OUT = process.argv[2] || "shots";
const PERSONA = process.argv[3] || "P02";
const BASE = "http://127.0.0.1:8600";
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function clickText(page, tag, text) {
  const handles = await page.$$(tag);
  for (const h of handles) {
    const t = (await page.evaluate((el) => el.textContent || "", h)).trim();
    if (t === text) {
      await h.click();
      return true;
    }
  }
  return false;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
  await page.goto(BASE + "/", { waitUntil: "networkidle0" });
  await page.waitForSelector("header select");
  await page.select("header select", PERSONA);
  await sleep(4000); // run, brief job, fonts
  await page.screenshot({ path: path.join(OUT, "dashboard.png") });
  await page.screenshot({ path: path.join(OUT, "dashboard-full.png"), fullPage: true });

  // Evidence pop-up: the first "K" marker of the options table.
  if (await clickText(page, "button", "K")) {
    await sleep(800);
    const dialog = await page.$("[role='dialog']");
    if (dialog) await dialog.screenshot({ path: path.join(OUT, "evidence.png") });
    await page.screenshot({ path: path.join(OUT, "evidence-page.png") });
    await page.keyboard.press("Escape");
    await sleep(400);
  } else {
    console.log("no K button");
  }

  if (await clickText(page, "button", "Dağılım")) {
    await sleep(800);
    // hide the fixed approval bar so that it does not cover the section
    await page.addStyleTag({ content: ".fixed, .sticky { display: none !important; }" });
    const el = await page.$("section:has(button[aria-pressed])");
    if (el) await el.screenshot({ path: path.join(OUT, "allocation.png") });
  } else {
    console.log("no Dağılım button");
  }

  const runId = await page.evaluate(() => {
    const a = [...document.querySelectorAll("a[href*='/meeting/']")][0];
    return a ? a.getAttribute("href").split("/meeting/")[1] : null;
  });
  console.log("run id from link:", runId);
  if (runId) {
    const m = await browser.newPage();
    await m.setViewport({ width: 1440, height: 900, deviceScaleFactor: 2 });
    await m.goto(BASE + "/meeting/" + runId, { waitUntil: "networkidle0" });
    await sleep(3000);
    await m.screenshot({ path: path.join(OUT, "meeting.png") });
  }
  await browser.close();
})().catch((e) => {
  console.error(e);
  process.exit(1);
});

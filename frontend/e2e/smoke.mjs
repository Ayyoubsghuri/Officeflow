// End-to-end smoke test of the built interface against the real Python server.
// Run `npm run build` first, then `npm run e2e` (needs Playwright with Chromium).
import { spawn } from "node:child_process";
import { mkdtempSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require("playwright");
const port = 8790 + Math.floor(Math.random() * 100);
const token = "e2e";
const work = mkdtempSync(join(tmpdir(), "officeflow-e2e-"));
const python = process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");
const server = spawn(python, ["../tests/ui_server.py", work, String(port), token], { stdio: "inherit" });
const base = `http://127.0.0.1:${port}`;
const failures = [];
const check = (ok, label) => {
  console.log(`${ok ? "✓" : "✗"} ${label}`);
  if (!ok) failures.push(label);
};

async function waitForServer() {
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(base)).ok) return;
    } catch {
      /* still starting */
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("server did not start");
}

try {
  await waitForServer();
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));

  await page.goto(`${base}/?token=${token}`);
  await page.waitForSelector(".fan-card");
  check((await page.$$(".fan-card")).length >= 20, "dashboard shows a folder per tool");

  await page.click(".fan-info");
  await page.waitForSelector("h1:has-text('PDF Smart Organizer')");
  await page.click("button:has-text('Folder')");
  await page.click("button:has-text('Use this folder')");
  await page.click("button:has-text('Preview')");
  await page.waitForSelector(".banner.info", { timeout: 20000 });
  check(true, "organizer preview");
  await page.click("button.primary:has-text('Run')");
  await page.waitForSelector(".banner.success, .banner.warning", { timeout: 20000 });
  check(true, "organizer run");

  await page.goto(`${base}/workflow/`);
  await page.waitForSelector(".flow-node");
  await page.click(".floatbar .create");
  await page.click(".addmenu-item:has-text('PDF Smart Organizer')");
  await page.click(".floatbar .create");
  const afterPdf = await page.$$eval(".addmenu-item .grow", (els) => els.map((e) => e.textContent));
  check(afterPdf.length > 0 && !afterPdf.some((n) => /Excel files|worksheets|Generate documents/.test(n)),
    "after a PDF step only PDF readers are offered");
  await page.click(".addmenu-item:has-text('Extract tables to Excel')");
  await page.click(".floatbar .create");
  const afterXlsx = await page.$$eval(".addmenu-item .grow", (els) => els.map((e) => e.textContent));
  check(afterXlsx.includes("Generate documents from Excel") && !afterXlsx.includes("Merge PDFs"),
    "after an Excel step only Excel readers are offered");
  await page.click(".addmenu-item:has-text('Generate formatted report')");
  await page.click(".flow-node:has-text('Extract tables to Excel')");
  await page.waitForSelector(".inspector .caption:has-text('Step 2')");
  await page.waitForTimeout(300);
  check(await page.$eval(".inspector button.danger", (b) => b.disabled),
    "removing a step that would break the chain is disabled");
  check((await page.$$(".fmtpill")).length >= 7, "nodes show input and output formats");

  await page.fill(".titleinput", "Smoke");
  await page.click(".builder-top button:has-text('Save')");
  await page.waitForSelector(".tag.green:has-text('Saved')");
  check(true, "workflow saved");

  for (const path of ["/toolbox/?cat=word", "/history/", "/logs/", "/settings/"]) {
    await page.goto(`${base}${path}`);
    await page.waitForTimeout(500);
  }
  check(errors.length === 0, `no browser errors${errors.length ? ": " + errors.join(" | ") : ""}`);
  await browser.close();
} catch (e) {
  console.error(e);
  failures.push(String(e));
} finally {
  server.kill();
}
process.exit(failures.length ? 1 : 0);

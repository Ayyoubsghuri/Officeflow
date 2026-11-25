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
const server = spawn(python, ["../tests/ui_server.py", work, String(port), token], {
  stdio: "inherit",
  env: { ...process.env, OFFICEFLOW_FAKE_AI: "1" },
});
const shot = async (page, name) => {
  if (process.env.SHOTS) await page.screenshot({ path: join(process.env.SHOTS, `${name}.png`) });
};
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
  await page.waitForSelector(".info");
  check((await page.$$(".fcard")).length === 0 && !(await page.$("text=Tools (")), "home shows workflows only, no tool cards");
  await page.goto(`${base}/tool/?id=pdf.organize`);
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
  await page.fill(".folderinput", "Invoices/2024");
  await page.click(".builder-top button:has-text('Save')");
  await page.waitForSelector(".tag.green:has-text('Saved')");
  check(true, "workflow saved");

  // Workflow library: folders, search, reopen; the dashboard now shows workflows as folders.
  await page.goto(`${base}/workflows/`);
  await page.waitForSelector(".tree-item:has-text('Invoices')");
  check((await page.$$(".tree-item:has-text('2024')")).length === 1, "library shows the folder tree");
  await page.click(".tree-item:has-text('Invoices')");
  await page.waitForSelector(".lib-card:has-text('2024')");
  await page.click(".lib-card:has-text('2024')");
  await page.waitForSelector(".lib-card:has-text('Smoke')");
  await page.waitForTimeout(700);
  await shot(page, "library");
  await page.fill(".lib-side input", "organizer");
  await page.waitForSelector("h1:has-text('Results for')");
  check((await page.$$(".lib-card:has-text('Smoke')")).length === 1, "search finds a workflow by one of its tools");
  await page.click(".lib-card:has-text('Smoke')");
  await page.waitForSelector(".flow-node:has-text('PDF Smart Organizer')");
  check((await page.inputValue(".folderinput")) === "Invoices/2024", "workflow opens from the library with its folder");
  check((await page.$$(".flow-node .tag:has-text('Result')")).length === 1, "the last step is marked as the result");
  await page.click(".flow-node:has-text('PDF Smart Organizer')");
  await page.click(".keepbox .check");
  await page.waitForSelector(".flow-node:has-text('PDF Smart Organizer') .tag:has-text('Kept')");
  check(true, "an earlier step can also be kept in the result");
  await page.waitForTimeout(400);
  await shot(page, "keep-step");
  await page.goto(`${base}/`);
  await page.waitForSelector(".fcard:has(.fcard-title:text-is('Invoices'))");
  check(true, "home shows workflow folders");
  await page.click(".fcard:has(.fcard-title:text-is('Invoices'))");
  await page.click(".fcard:has(.fcard-title:text-is('2024'))");
  await page.click(".fcard:has(.fcard-title:text-is('Smoke'))");
  await page.waitForSelector(".fcard.on:has(.fcard-title:text-is('Smoke'))");
  check((await page.textContent(".info")).includes("PDF Smart Organizer"), "Info panel shows the selected workflow's tools");
  await page.waitForTimeout(600);
  await shot(page, "home-selected");
  await page.click(".info button:has-text('Open workflow')");
  await page.waitForSelector(".flow-node:has-text('PDF Smart Organizer')");
  check(true, "a workflow folder on the home page opens the workflow");
  await page.goto(`${base}/`);
  await page.waitForSelector(".fcard:has(.fcard-title:text-is('Invoices'))");
  await page.waitForTimeout(800);
  await shot(page, "dashboard-workflows");

  // AI assistant (a fake model stands in for Claude in this test).
  await page.goto(`${base}/settings/`);
  await page.fill("#ai input[type=password]", "sk-ant-test-0123456789abcdefWXYZ");
  await page.click("#ai button:has-text('Save')");
  await page.waitForSelector("#ai .tag.green");
  check(!(await page.content()).includes("0123456789abcdef"), "API key is not shown back after saving");
  await page.goto(`${base}/assistant/`);
  await page.waitForSelector(".prompt");
  await page.fill(".prompt", "Sort the PDFs in C:\\Users\\ali\\Scans by reference, send to ali@x.ma");
  await page.click("button:has-text('Review before sending')");
  await page.waitForSelector(".sendbox pre");
  const sent = await page.textContent(".sendbox pre");
  check(sent.includes("<path-1>") && sent.includes("<email-1>") && !sent.includes("Users"),
    "paths and e-mails are hidden before sending");
  await page.waitForTimeout(300);
  await shot(page, "ai-review");
  await page.click(".sendbox button.primary");
  // Leave while the AI works: it keeps going, says when it is done, and the answer waits on the page.
  await page.waitForSelector("text=You can go to other pages meanwhile");
  await page.click(".rail a[href='/workflows/']");
  await page.waitForSelector(".nav-dot.busy");
  await page.waitForSelector(".toast:has-text('The AI assistant has finished')", { timeout: 20000 });
  check(!!(await page.$(".nav-dot:not(.busy)")), "AI keeps working on another page and says when it is done");
  await page.click(".rail a[href='/assistant/']");
  await page.waitForSelector("text=Open in Workflow Builder", { timeout: 20000 });
  check((await page.$$(".ai-step")).length === 2, "AI proposes a two-step workflow");
  check(!(await page.$(".nav-dot")), "the answer is marked as seen");
  await page.waitForTimeout(400);
  await shot(page, "ai-workflow");
  await page.click("text=Open in Workflow Builder");
  await page.waitForSelector(".flow-node:has-text('Search text in PDFs')");
  check((await page.$$(".flow-node")).length === 3, "AI draft opens in the builder");
  await page.waitForTimeout(500);
  await shot(page, "ai-builder");
  // Back on the assistant page the proposed workflow is still there; create the missing tool from it.
  await page.goto(`${base}/assistant/`);
  await page.waitForSelector("text=Missing tool: OCR");
  check(true, "the proposed workflow is kept when coming back to the assistant");
  await page.click("button:has-text('Create this tool')");
  await page.waitForSelector("text=Workflow waiting for a new tool");
  check((await page.inputValue(".prompt")).startsWith("OCR:"), "the missing tool's description becomes the plugin request");
  await page.click("button:has-text('Review before sending')");
  await page.click(".sendbox button.primary");
  await page.waitForSelector("text=Safety check passed", { timeout: 20000 });
  check(await page.$eval("button:has-text('Install plugin')", (b) => b.disabled), "install needs explicit approval");
  await page.click("text=I have read this code");
  await shot(page, "ai-plugin");
  await page.click("button:has-text('Install plugin')");
  await page.waitForSelector("text=Plugin installed");
  await page.waitForSelector("text=Continue your workflow");
  await shot(page, "ai-continue");
  await page.click("button:has-text('Rebuild the workflow with the new tool')");
  await page.waitForSelector(".sendbox pre");
  check((await page.textContent(".sendbox pre")).includes("Sort the PDFs in <path-1>"),
    "rebuilding brings back the original workflow request for review");
  await page.goto(`${base}/assistant/`);
  await page.waitForSelector(".activity");
  await page.click(".activity >> nth=1");
  await page.waitForSelector(".activity button:has-text('Open in Workflow Builder')");
  check(true, "an earlier workflow can be reopened from Activity");
  await page.goto(`${base}/tool/?id=pdf.count_pages_test`);
  await page.waitForSelector("h1:has-text('Count pages')");
  check(true, "AI-written tool installed and opened");
  await page.goto(`${base}/assistant/`);
  await page.waitForSelector(".activity");
  check((await page.$$(".activity")).length === 2, "activity log lists what was sent");

  // Switch to OpenAI: separate key, model list from the account, same review-before-send flow.
  await page.goto(`${base}/settings/`);
  await page.click("#ai .segmented button:has-text('OpenAI')");
  await page.waitForSelector("#ai label:has-text('OpenAI API key')");
  await page.fill("#ai input[type=password]", "sk-proj-test-0123456789abcdefOPEN");
  await page.click("#ai button:has-text('Save')");
  await page.waitForSelector("#ai .tag.green:has-text('OpenAI')");
  await page.click("#ai button:has-text('Load my models')");
  await page.waitForSelector("#ai datalist option[value='gpt-5-mini']", { state: "attached" });
  await page.fill("#ai input[list]", "gpt-5-mini");
  await page.press("#ai input[list]", "Enter");
  await page.waitForTimeout(400);
  await shot(page, "openai-settings");
  await page.goto(`${base}/assistant/`);
  await page.waitForSelector(".pill:has-text('OpenAI')");
  check((await page.textContent(".pill:has-text('OpenAI')")).includes("gpt-5-mini"), "assistant shows the OpenAI model");
  await page.fill(".prompt", "Sort PDFs by reference");
  await page.click("button:has-text('Review before sending')");
  await page.waitForSelector(".sendbox button:has-text('gpt-5-mini')");
  await page.click(".sendbox button.primary");
  await page.waitForSelector("text=Open in Workflow Builder", { timeout: 20000 });
  check(true, "OpenAI provider designs a workflow");
  await page.goto(`${base}/assistant/`);
  await page.waitForSelector(".activity");
  check((await page.textContent(".activity")).length > 0 &&
    (await page.$$eval(".activity .faint", (els) => els.some((e) => e.textContent.includes("openai/gpt-5-mini")))),
    "activity log records the OpenAI request");

  // NVIDIA through the OpenAI-compatible path: key, model typed in the search field, workflow.
  await page.goto(`${base}/settings/`);
  await page.click("#ai .segmented button:has-text('NVIDIA')");
  await page.waitForSelector("#ai label:has-text('NVIDIA API key')");
  await page.fill("#ai input[type=password]", "nvapi-test-0123456789abcdefNVID");
  await page.click("#ai button:has-text('Save')");
  await page.waitForSelector("#ai .tag.green:has-text('NVIDIA')");
  await page.fill("#ai input[list]", "meta/llama-3.3-70b-instruct");
  await page.press("#ai input[list]", "Enter");
  await page.waitForTimeout(400);
  await shot(page, "nvidia-settings");
  await page.goto(`${base}/assistant/`);
  await page.waitForSelector(".pill:has-text('NVIDIA')");
  check((await page.textContent(".pill:has-text('NVIDIA')")).includes("meta/llama-3.3-70b-instruct"),
    "assistant shows the NVIDIA model");
  await page.fill(".prompt", "Sort PDFs by reference");
  await page.click("button:has-text('Review before sending')");
  await page.click(".sendbox button.primary");
  await page.waitForSelector("text=Open in Workflow Builder", { timeout: 20000 });
  check(true, "NVIDIA provider designs a workflow");

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

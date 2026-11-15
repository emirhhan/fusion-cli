// Derlenmiş masaüstü arayüzü (app/dist) üretim CSP'siyle gerçek Chromium'da açılır;
// paketle gelen script/stil/font/görsel engelleniyorsa ihlal olarak raporlanır.
import { chromium } from "../../app/node_modules/playwright/index.mjs";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";

const dist = process.argv[2];
const shot = process.argv[3];
const conf = JSON.parse(await readFile(process.argv[4], "utf8"));
const csp = Object.entries(conf.app.security.csp).map(([k, v]) => `${k} ${v}`).join("; ");
const TYPES = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
  ".png": "image/png", ".woff2": "font/woff2", ".json": "application/json", ".webp": "image/webp", ".jpg": "image/jpeg" };

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
const violations = [];
const errors = [];
await page.exposeFunction("__cspIhlal", (v) => violations.push(v));
await page.addInitScript(() => {
  document.addEventListener("securitypolicyviolation", (e) =>
    window.__cspIhlal(`${e.violatedDirective} ← ${e.blockedURI || "inline"}`));
});
page.on("pageerror", (e) => errors.push(String(e.message)));
await page.route("http://fusion.test/**", async (route) => {
  let path = new URL(route.request().url()).pathname;
  if (path === "/") path = "/index.html";
  const file = normalize(join(dist, path));
  try {
    const body = await readFile(file);
    await route.fulfill({ status: 200, body, headers: { "content-type": TYPES[extname(file)] || "application/octet-stream", "content-security-policy": csp } });
  } catch {
    await route.fulfill({ status: 404, body: "" });
  }
});
await page.goto("http://fusion.test/");
await page.waitForTimeout(2500);
await page.screenshot({ path: shot });
const fonts = await page.evaluate(async () => { await document.fonts.ready; return [...document.fonts].filter((f) => f.status === "loaded").length; });
const text = (await page.evaluate(() => document.body.innerText)).slice(0, 200).replace(/\s+/g, " ");
console.log(JSON.stringify({ violations, errors: errors.slice(0, 5), fonts, text }));
await browser.close();

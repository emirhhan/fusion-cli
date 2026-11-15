import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { chromium, webkit } from "@playwright/test";

const indexHtml = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const security = JSON.parse(readFileSync(new URL("../src-tauri/tauri.conf.json", import.meta.url), "utf8")).app.security;

// Both the HTML meta policy and Tauri's response policy are enforced. In a browser,
// route the Windows form of the registered native protocol to a controlled page.
for (const [engine, browserType] of Object.entries({ chromium, webkit })) {
  test(`${engine}: HTML preview survives both app policies and retains its opaque sandbox`, async () => {
    const browser = await browserType.launch({ headless: true });
    try {
      const page = await browser.newPage();
      let remoteRequests = 0;
      await page.route("**/*", async (route) => {
        const url = route.request().url();
        if (url === "http://fusion-app.localhost/") {
          await route.fulfill({ contentType: "text/html; charset=utf-8", headers: {
            "Content-Security-Policy": Object.entries(security.csp).map(([directive, sources]) => `${directive} ${sources}`).join("; "),
          }, body: indexHtml.replace(/<script\b[^>]*>[\s\S]*?<\/script>/g, "") });
        } else if (url === "http://fusion-preview.localhost/test-key") {
          await route.fulfill({ contentType: "text/html; charset=utf-8", body: `<h1>Preview visible</h1><script>
            let isolated = false; try { parent.document.body; } catch { isolated = true; }
            document.body.dataset.isolated = String(isolated);
            document.body.dataset.origin = window.origin;
            document.body.dataset.bridge = String(typeof window.__TAURI_INTERNALS__);
          </script>` });
        } else {
          if (url.startsWith("https://untrusted.example/")) remoteRequests++;
          await route.abort();
        }
      });
      await page.goto("http://fusion-app.localhost/");
      await page.evaluate(() => {
        const frame = document.createElement("iframe");
        frame.sandbox = "allow-scripts";
        frame.src = "http://fusion-preview.localhost/test-key";
        document.body.append(frame);
      });
      const frame = page.frameLocator("iframe").first();
      assert.equal(await frame.locator("h1").innerText({ timeout: 2000 }), "Preview visible");
      assert.equal(await frame.locator("body").getAttribute("data-isolated"), "true");
      assert.equal(await frame.locator("body").getAttribute("data-origin"), "null");
      assert.equal(await frame.locator("body").getAttribute("data-bridge"), "undefined");
      const remoteBlocked = await page.evaluate(() => new Promise((resolve) => {
        const finish = (blocked) => {
          clearTimeout(timer);
          document.removeEventListener("securitypolicyviolation", onViolation);
          resolve(blocked);
        };
        const onViolation = (event) => {
          if (event.blockedURI.startsWith("https://untrusted.example")) finish(true);
        };
        const timer = setTimeout(() => finish(false), 2000);
        document.addEventListener("securitypolicyviolation", onViolation);
        const frame = document.createElement("iframe");
        frame.src = "https://untrusted.example/private";
        document.body.append(frame);
      }));
      assert.equal(remoteBlocked, true, "remote frame must trigger a CSP violation");
      assert.equal(remoteRequests, 0, "remote frames remain blocked before any request");
      if (engine === "webkit") {
        // Playwright has no registered native scheme handler. WebKit's unsupported
        // protocol error is expected; a CSP rejection must not precede it.
        const protocolMessage = page.waitForEvent("console", {
          predicate: (message) => message.text().includes("custom protocol") || message.text().includes("fusion-preview://"),
          timeout: 2000,
        });
        await page.evaluate(() => {
          const frame = document.createElement("iframe");
          frame.sandbox = "allow-scripts";
          frame.src = "fusion-preview://localhost/test-key";
          document.body.append(frame);
        });
        assert.match((await protocolMessage).text(), /custom protocol and comes from a sandboxed iframe/,
          "CSP must allow the scheme through to WebKit's unregistered-protocol check");
      }
    } finally {
      await browser.close();
    }
  });
}

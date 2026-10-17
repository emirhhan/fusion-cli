import { chromium, expect, test, type BrowserContext, type Page } from "@playwright/test";
import { createServer, type Server } from "node:http";
import { existsSync, mkdtempSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const extensionPath = resolve(process.cwd(), "../chrome-extension");

/** Playwright'ın indirdiği Chrome for Testing (eklenti yüklemeyi destekler; markalı Chrome desteklemez). */
function chromiumPath(): string | undefined {
  if (process.env.FUSION_E2E_CHROMIUM) return process.env.FUSION_E2E_CHROMIUM;
  const cache = join(process.env.HOME ?? "", "Library/Caches/ms-playwright");
  if (!existsSync(cache)) return undefined;
  for (const dir of readdirSync(cache).filter((d) => /^chromium-\d+$/.test(d)).sort().reverse()) {
    const exe = join(cache, dir, "chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing");
    if (existsSync(exe)) return exe;
  }
  return undefined;
}

const PAGES: Record<string, string> = {
  "/login": `<h1>Giriş</h1><form action="/login" method="post"><label>Kullanıcı <input name="user"></label>
    <label>Parola <input type="password" name="password"></label><button type="submit">Giriş yap</button></form>`,
  "/panel": `<h1>Hesabım</h1><p>Hoş geldin, test kullanıcısı</p><a href="/form">Forma git</a>`,
  "/form": `<h1>Kampanya formu</h1><form action="/thanks" method="get"><label>Ad <input name="ad"></label>
    <label>Dönem <select name="donem"><option value="7">Son 7 gün</option><option value="30">Son 30 gün</option></select></label>
    <label><input type="checkbox" name="onay"> Koşulları okudum</label><button type="submit">Gönder</button></form>`,
  "/thanks": `<h1>Teşekkürler</h1><p id="sonuc">form alındı</p>`,
  "/register": `<h1>Kayıt</h1><label>E-posta <input name="email"></label><a href="/register2">Devam</a>`,
  "/register2": `<h1>Kayıt adım 2</h1><button id="hesap">Hesap oluştur</button>`,
  "/dnd": `<h1>Sürükle</h1><div id="a" draggable="true">Öğe A</div><div id="zone" style="height:80px;border:1px solid">Bırak</div>
    <p id="durum">bekliyor</p><script>
    const z=document.getElementById('zone');z.addEventListener('dragover',e=>e.preventDefault());
    z.addEventListener('drop',e=>{e.preventDefault();document.getElementById('durum').textContent='bırakıldı';});</script>`,
  "/mouse": `<h1>Fare</h1><button id="d">Çift tıkla</button><p id="n">0</p><div id="r">Sağ tıkla</div><p id="m">menü yok</p><div id="s" style="height:60px;overflow:auto"><div style="height:600px">uzun</div></div>
    <script>document.getElementById('d').addEventListener('dblclick',()=>document.getElementById('n').textContent='çift');
    document.getElementById('r').addEventListener('contextmenu',e=>{e.preventDefault();document.getElementById('m').textContent='menü açıldı';});</script>`,
};

let server: Server;
let origin = "";
let context: BrowserContext;
let panel: Page;

test.beforeAll(async () => {
  server = createServer((req, res) => {
    const path = (req.url ?? "/").split("?")[0];
    if (req.method === "POST" && path === "/login") {
      res.writeHead(302, { Location: "/panel", "Set-Cookie": "oturum=1; Path=/" });
      res.end();
      return;
    }
    const body = PAGES[path];
    res.writeHead(body ? 200 : 404, { "Content-Type": "text/html; charset=utf-8" });
    res.end(`<!doctype html><meta charset="utf-8"><title>${path}</title>${body ?? "yok"}`);
  });
  await new Promise<void>((done) => server.listen(0, "127.0.0.1", done));
  origin = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
  context = await chromium.launchPersistentContext(mkdtempSync(join(tmpdir(), "fusion-ext-")), {
    executablePath: chromiumPath(),
    headless: false,
    args: [`--disable-extensions-except=${extensionPath}`, `--load-extension=${extensionPath}`],
  });
  const worker = context.serviceWorkers()[0] ?? (await context.waitForEvent("serviceworker"));
  const id = new URL(worker.url()).host;
  panel = await context.newPage();
  await panel.goto(`chrome-extension://${id}/panel.html`);
});

test.afterAll(async () => {
  await context?.close();
  server?.close();
});

/** Fusion'ın köprüden gönderdiği komutla aynı yol: arka plan `fusion.exec`. */
async function exec(islem: string, veri: Record<string, unknown> = {}) {
  const reply = await panel.evaluate(
    (command) => chrome.runtime.sendMessage({ type: "fusion.exec", command }),
    { id: "t", islem, veri },
  );
  if (!reply?.ok) throw new Error(reply?.hata ?? "komut başarısız");
  return reply.veri as Record<string, any>;
}
const refOf = async (query: string) => {
  const found = await exec("find", { query });
  const el = (found.elements ?? found.matches ?? [])[0];
  if (!el) throw new Error(`öğe yok: ${query}`);
  return el.ref as string;
};
const text = async () => String((await exec("snapshot")).text ?? "");

test("giriş formu: kullanıcı adı yazılır, parola alanına yazma engellenir", async () => {
  await exec("tab_open", { url: `${origin}/login` });
  await exec("type", { ref: await refOf("Kullanıcı"), text: "emirhan" });
  const snap = await exec("snapshot");
  const parola = (snap.elements as any[]).find((e) => /parola|password/i.test(e.name ?? ""));
  if (parola) await expect(exec("type", { ref: parola.ref, text: "x" })).rejects.toThrow();
  await exec("click", { ref: await refOf("Giriş yap") });
  expect(await text()).toContain("Hoş geldin");
});

test("çok sayfalı akış: panelden forma git, doldur, seç, işaretle, gönder", async () => {
  await exec("click", { ref: await refOf("Forma git") });
  await exec("type", { ref: await refOf("Ad"), text: "Kampanya 1" });
  await exec("select", { ref: await refOf("Dönem"), value: "30" });
  await exec("click", { ref: await refOf("Koşulları okudum") });
  await exec("click", { ref: await refOf("Gönder") });
  expect(await text()).toContain("form alındı");
  const url = String((await exec("snapshot")).url);
  expect(url).toContain("ad=Kampanya+1");
  expect(url).toContain("donem=30");
  expect(url).toContain("onay=on");
});

test("kayıt akışı: iki adım gezinir, onay gerektiren 'Hesap oluştur' düğmesini görür", async () => {
  await exec("navigate", { url: `${origin}/register` });
  await exec("type", { ref: await refOf("E-posta"), text: "a@b.co" });
  await exec("click", { ref: await refOf("Devam") });
  const desc = await exec("describe", { ref: await refOf("Hesap oluştur") });
  expect(desc.name).toMatch(/Hesap oluştur/);
});

test("çift tıklama, sağ tıklama ve fare tekerleği", async () => {
  await exec("navigate", { url: `${origin}/mouse` });
  await exec("click", { ref: await refOf("Çift tıkla"), kind: "double" });
  await exec("click", { ref: await refOf("Sağ tıkla"), kind: "right" });
  const t = await text();
  expect(t).toContain("çift");
  expect(t).toContain("menü açıldı");
  const wheel = await exec("wheel", { dx: 0, dy: 300 });
  expect(wheel.wheel).toEqual([0, 300]);
});

test("sürükle-bırak", async () => {
  await exec("navigate", { url: `${origin}/dnd` });
  await exec("drag", { ref: await refOf("Öğe A"), to_ref: await refOf("Bırak") });
  expect(await text()).toContain("bırakıldı");
});

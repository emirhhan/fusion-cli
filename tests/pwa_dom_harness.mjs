// PWA görünüm senaryoları (jsdom); tests/test_remote_pwa_views.py çalıştırır.
import { pathToFileURL } from "node:url";

const [dir, jsdomPath] = process.argv.slice(2);
const { JSDOM } = await import(pathToFileURL(jsdomPath).href);
const dom = new JSDOM("<!doctype html><body><div id='kok'></div></body>", { pretendToBeVisual: true });
globalThis.window = dom.window;
globalThis.document = dom.window.document;
const load = (name) => import(pathToFileURL(`${dir}/${name}`).href);
const { renderChats } = await load("views-chats.js");
const { approvalCard } = await load("approvals.js");
const out = {};

// 1) Yeniden çizim yeni proje formundaki yazıyı ve açık durumu silmez
{
  const ctx = { tasks: [], chats: [], projects: [], chatProjects: {}, filter: "all" };
  const root = document.getElementById("kok");
  const handlers = { open() {}, onProjectCreate: async () => true };
  renderChats(ctx, root, handlers);
  root.querySelector("[aria-label='Proje ekle']").click();
  let input = root.querySelector("input");
  input.focus();
  input.value = "Yeni oyun";
  input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  renderChats(ctx, root, handlers); // 4 sn / 20 sn yoklaması
  input = root.querySelector("input");
  out.draft = {
    value: input.value,
    formHidden: root.querySelector("form").hidden,
    focused: document.activeElement === input,
  };
}

const rpc = async () => ({ ok: true, data: {} });
const buttons = (card) => [...card.querySelectorAll(".approval-actions button")].map((b) => b.textContent);

// 2) args nesne ise ayrıntı gizlenmez
{
  const card = approvalCard({ questionId: "q1", title: "Dosya yaz", args: { path: "a.txt", content: "x" } }, rpc, () => {});
  out.argsObject = { details: Boolean(card.querySelector(".approval-details")), text: card.querySelector(".approval-details pre")?.textContent ?? "" };
}

// 3) tanınmayan seçenekler: Reddet daima var, açıklama yazılır
{
  const card = approvalCard({ questionId: "q2", title: "X", options: ["bilinmeyen_secenek"] }, rpc, () => {});
  out.unknownOptions = { buttons: buttons(card), note: card.textContent.includes("tanınmıyor") };
}
{
  const card = approvalCard({ questionId: "q3", title: "X", options: ["once"] }, rpc, () => {});
  out.onceOnly = buttons(card);
}

// 4) danger ve reason birlikte gösterilir
{
  const card = approvalCard({ questionId: "q4", title: "X", danger: "Geri alınamaz", reason: "Dosya silinecek" }, rpc, () => {});
  out.both = card.textContent.includes("Geri alınamaz") && card.textContent.includes("Dosya silinecek");
}
console.log(JSON.stringify(out));
process.exit(0);

import { approvalCard, pendingFromEvents } from "./approvals.js";
import { ACTIVE_STATES, h, icon } from "./dom.js";
import { prepareAttachment, renderRichText } from "./media.js";
import { createDictation } from "./voice.js";

const POLL_MS = 1200;
const HISTORY_RETRY_MS = 3000;

export function newChatId() {
  return `c_${crypto.randomUUID().replaceAll("-", "").slice(0, 20)}`;
}

// Sohbet ekranı: geçmiş + canlı görev akışı + mesaj kutusu (ek, ses, durdurma, model).
export function createChat({ rpc, root, ctx, onBack, onChange, toast }) {
  let chat = null;
  let run = null;
  let afterSeq = 0;
  let stream = null;
  let timer = null;
  let open = false;
  let polling = null;
  let attachments = [];
  const answered = new Set();

  const list = h("div", { class: "msgs", role: "log", "aria-live": "polite" });
  const typing = h("div", { class: "bubble assistant typing", hidden: true }, h("span"), h("span"), h("span"));
  const title = h("div", { class: "bar-title" }, "Sohbet");
  const back = h("button", { class: "bar-btn", type: "button", "aria-label": "Sohbetler" }, icon("back"));
  const projectSelect = h("select", { class: "pick", "aria-label": "Proje" });
  const modelSelect = h("select", { class: "pick", "aria-label": "Model" });
  const picks = h("div", { class: "picks" }, projectSelect, modelSelect);
  const chips = h("div", { class: "chips", hidden: true });
  const input = h("textarea", { id: "mesaj", rows: "1", placeholder: "Fusion'a yaz…", "aria-label": "Mesaj" });
  const fileInput = h("input", { type: "file", accept: "image/*,.txt,.md,.json,.csv,.log,.py,.js,.ts", multiple: true, hidden: true });
  const attach = h("button", { class: "round ghost", type: "button", "aria-label": "Dosya veya görsel ekle" }, icon("plus"));
  const mic = h("button", { class: "round ghost", type: "button", "aria-label": "Sesle yaz", hidden: true }, icon("mic"));
  const send = h("button", { class: "round", type: "button", "aria-label": "Gönder" }, icon("send"));
  const composer = h("div", { class: "composer" }, attach, input, mic, send);
  root.replaceChildren(
    h("header", { class: "bar" }, back, title, h("span", { class: "bar-btn" })),
    picks, list, chips, composer, fileInput,
  );
  list.append(typing);

  const dictation = createDictation({
    onText: (text) => { input.value = text; grow(); },
    onState: (state, detail) => {
      mic.classList.toggle("on", state === "listening");
      if (state === "error") toast(detail === "not-allowed" ? "Mikrofon izni verilmedi." : "Ses tanıma hatası.");
    },
  });
  if (dictation) { mic.hidden = false; mic.addEventListener("click", () => dictation.toggle()); }

  back.addEventListener("click", () => { close(); onBack(); });
  attach.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", addFiles);
  send.addEventListener("click", () => (running() ? stop() : submit()));
  input.addEventListener("input", grow);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !running()) { event.preventDefault(); submit(); }
  });
  projectSelect.addEventListener("change", async () => {
    const result = await rpc("chats.assign", { chatId: chat.chatId, projectId: projectSelect.value || null });
    if (!result.ok) return toast(result.message || "Proje atanamadı.");
    chat.projectId = projectSelect.value || null;
    onChange();
  });
  modelSelect.addEventListener("change", () => { ctx.tier = modelSelect.value; localStorage.setItem("fusion.tier", ctx.tier); toast(`Model: ${modelSelect.selectedOptions[0].textContent}`); });

  const running = () => Boolean(run) && ACTIVE_STATES.includes(run.state);
  function grow() { input.rows = Math.min(5, input.value.split("\n").length); }
  function scrollEnd() { list.scrollTop = list.scrollHeight; }
  function syncButton() {
    const active = running();
    send.replaceChildren(icon(active ? "stop" : "send"));
    send.setAttribute("aria-label", active ? "Durdur" : "Gönder");
    send.classList.toggle("stop", active);
  }

  function bubble(kind, content) {
    const el = h("div", { class: `bubble ${kind}` }, content);
    typing.before(el);
    return el;
  }
  const richBubble = (kind, text) => bubble(kind, renderRichText(text, rpc));

  function fillSelects() {
    projectSelect.replaceChildren(h("option", { value: "" }, "Projesiz"), ...ctx.projects.map((p) => h("option", { value: p.id }, p.name)));
    projectSelect.value = chat?.projectId ?? "";
    modelSelect.hidden = ctx.tiers.length === 0;
    modelSelect.replaceChildren(...ctx.tiers.map((t) => h("option", { value: t.name }, t.label)));
    modelSelect.value = ctx.tier || ctx.activeTier || "";
  }

  function renderChips() {
    chips.hidden = attachments.length === 0;
    chips.replaceChildren(...attachments.map((item, index) => h("span", { class: "chip-att" },
      item.preview ? h("img", { src: item.preview, alt: "" }) : null, item.name,
      h("button", { type: "button", "aria-label": "Eki kaldır", onclick: () => { attachments.splice(index, 1); renderChips(); } }, icon("close")))));
  }

  async function addFiles() {
    for (const file of fileInput.files) {
      try { attachments.push(await prepareAttachment(file)); } catch (error) { toast(error.message); }
    }
    fileInput.value = "";
    renderChips();
  }

  function apply(event) {
    const p = event.payload ?? {};
    if (event.kind === "delta") {
      stream ??= bubble("assistant", "");
      stream.textContent += p.text ?? "";
    } else if (event.kind === "event") {
      if (p.olay === "ToolExecuted") typing.before(h("div", { class: "step" }, `${p.name ?? "araç"} · ${p.outcome ?? "ok"}`));
      else if (p.olay === "ErrorOccurred") bubble("error", String(p.message ?? "Hata"));
    } else if (event.kind === "done") {
      const text = p.summary || stream?.textContent || "";
      if (stream) { stream.replaceChildren(...renderRichText(text, rpc)); } else if (text) richBubble("assistant", text);
      stream = null;
    } else if (event.kind === "failed") { stream = null; bubble("error", p.summary || "Görev başarısız oldu."); }
    else if (event.kind === "cancelled") { stream = null; typing.before(h("div", { class: "step" }, "Görev durduruldu")); }
    else if (event.kind === "approval_answered") {
      answered.add(p.questionId);
      list.querySelector(`[data-question="${CSS.escape(String(p.questionId))}"]`)?.remove();
    }
  }

  async function poll() {
    clearTimeout(timer);
    if (!open || !run || polling === chat.token) return;
    const token = chat.token;
    const runId = run.runId;
    polling = token;
    try {
      const result = await rpc("tasks.events", { runId, afterSeq });
      if (!open || chat?.token !== token || run?.runId !== runId) return;
      if (!result.ok) throw new Error(result.message || "Görev akışı alınamadı.");
      const events = result.data?.events ?? [];
      for (const event of events) { apply(event); afterSeq = Math.max(afterSeq, event.seq); }
      run = { ...run, state: result.data?.state ?? run.state };
      for (const [, q] of pendingFromEvents(events)) {
        if (!answered.has(q.questionId) && !list.querySelector(`[data-question="${CSS.escape(String(q.questionId))}"]`)) {
          typing.before(approvalCard(q, rpc, () => { onChange(); poll(); }));
        }
      }
      typing.hidden = !["queued", "running"].includes(run.state);
      syncButton();
      if (events.length) scrollEnd();
      if (running()) timer = setTimeout(poll, POLL_MS);
      else onChange();
    } catch (error) {
      if (!open || chat?.token !== token) return;
      if (error.auth) { open = false; return onChange(true); }
      timer = setTimeout(poll, POLL_MS * 2);
    } finally {
      if (polling === token) {
        polling = null;
        if (open && chat?.token === token && run?.runId !== runId) void poll();
      }
    }
  }

  async function loadHistory(token) {
    const result = await rpc("chats.history", { chatId: chat.chatId, root: chat.root });
    if (!open || token !== chat?.token || run) return;
    if (result.ok) {
      for (const m of result.data.messages) m.role === "user" ? bubble("user", m.text) : richBubble("assistant", m.text);
      scrollEnd();
    } else if (result.error === "mesgul") {
      const note = h("div", { class: "step" }, "Görev çalışıyor; geçmiş bitince yüklenecek…");
      typing.before(note);
      setTimeout(() => { note.remove(); if (open && token === chat?.token && !run) void loadHistory(token); }, HISTORY_RETRY_MS);
    }
  }

  async function submit() {
    const text = input.value.trim();
    if (!text && attachments.length === 0) return;
    const sending = attachments;
    input.value = ""; grow(); attachments = []; renderChips();
    const ids = [];
    for (const item of sending) {
      const up = await rpc("uploads.put", { name: item.name, kind: item.kind, dataBase64: item.dataBase64 });
      if (!up.ok) return bubble("error", up.message || "Ek yüklenemedi.");
      ids.push(up.data.uploadId);
    }
    bubble("user", [text, ...sending.map((a) => h("div", { class: "att-note" }, a.preview ? h("img", { src: a.preview, alt: "" }) : `📎 ${a.name}`))]);
    scrollEnd();
    const result = await rpc("tasks.create", {
      prompt: text || "Ekleri incele.",
      chatId: chat.chatId, projectId: chat.projectId || undefined, root: chat.root || undefined,
      tier: ctx.tier || undefined, attachments: ids, idempotencyKey: crypto.randomUUID(),
    });
    if (!result.ok) return bubble("error", result.message || "Gönderilemedi.");
    run = result.data; afterSeq = 0; stream = null; typing.hidden = false; syncButton();
    onChange();
    void poll();
  }

  async function stop() {
    if (!run) return;
    const result = await rpc("tasks.cancel", { runId: run.runId });
    if (!result.ok) toast(result.message || "Durdurulamadı.");
    void poll();
  }

  function close() { open = false; clearTimeout(timer); }

  return {
    // chat: { chatId, root, projectId, title, runId?/run?, isNew }
    show(next) {
      close();
      chat = { ...next, token: Math.random() };
      run = next.run ? { ...next.run } : null;
      afterSeq = 0; stream = null; attachments = []; answered.clear(); renderChips();
      for (const node of [...list.children]) if (node !== typing) node.remove();
      typing.hidden = true;
      title.textContent = next.title || "Yeni sohbet";
      fillSelects();
      syncButton();
      open = true;
      if (run) { bubble("user", run.summary); void poll(); } else if (!next.isNew) void loadHistory(chat.token);
      if (next.isNew) input.focus();
    },
    reconcile(tasks) {
      if (!open || !chat) return;
      const next = tasks.find((item) => item.chatId === chat.chatId && ACTIVE_STATES.includes(item.state));
      if (!next || next.runId === run?.runId) return;
      run = { ...next };
      afterSeq = 0;
      stream = null;
      syncButton();
      void poll();
    },
    refreshSelects: fillSelects,
    close,
  };
}

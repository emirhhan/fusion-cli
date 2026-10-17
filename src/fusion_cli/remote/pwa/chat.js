import { approvalCard, pendingFromEvents } from "./approvals.js";
import { h, icon, ACTIVE_STATES } from "./dom.js";

const POLL_MS = 2000;

// Sohbet ekranı: bir görevin olay akışı mesaj balonlarına çevrilir. `run` yoksa boş yeni sohbettir.
export function createChat({ rpc, root, onBack, onCreated, onChange }) {
  let run = null;
  let afterSeq = 0;
  let timer = null;
  let open = false;
  const answered = new Set();

  const list = h("div", { class: "msgs", role: "log", "aria-live": "polite" });
  const typing = h("div", { class: "bubble assistant typing", hidden: true }, h("span"), h("span"), h("span"));
  const title = h("div", { class: "bar-title" }, "Yeni sohbet");
  const input = h("textarea", { id: "mesaj", rows: "1", placeholder: "Fusion'a yaz…", "aria-label": "Mesaj" });
  const send = h("button", { class: "send", type: "button", "aria-label": "Gönder" }, icon("send"));
  const back = h("button", { class: "bar-btn", type: "button", "aria-label": "Sohbetler" }, icon("back"));
  back.addEventListener("click", () => { close(); onBack(); });

  const hint = h("p", { class: "muted center small" }, "Yazdığın her mesaj Fusion'da yeni bir görev başlatır.");
  const composer = h("div", { class: "composer" }, input, send);
  root.replaceChildren(h("header", { class: "bar" }, back, title, h("span", { class: "bar-btn" })), list, hint, composer);
  list.append(typing);

  input.addEventListener("input", () => { input.rows = Math.min(5, input.value.split("\n").length); });
  send.addEventListener("click", submit);

  function scrollEnd() { list.scrollTop = list.scrollHeight; }

  function bubble(kind, text) {
    const el = h("div", { class: `bubble ${kind}` }, text);
    typing.before(el);
    return el;
  }

  function apply(event) {
    const p = event.payload ?? {};
    if (event.kind === "event") {
      if (p.olay === "ToolExecuted") typing.before(h("div", { class: "step" }, `${p.name ?? "araç"} · ${p.outcome ?? "ok"}`));
      else if (p.olay === "ErrorOccurred") bubble("error", String(p.message ?? "Hata"));
    } else if (event.kind === "done") {
      if (p.summary) bubble("assistant", p.summary);
    } else if (event.kind === "failed") bubble("error", p.summary || "Görev başarısız oldu.");
    else if (event.kind === "cancelled") typing.before(h("div", { class: "step" }, "Görev iptal edildi"));
    else if (event.kind === "approval_answered") {
      answered.add(p.questionId);
      list.querySelector(`[data-question="${CSS.escape(String(p.questionId))}"]`)?.remove();
    }
  }

  async function poll() {
    if (!open || !run) return;
    try {
      const result = await rpc("tasks.events", { runId: run.runId, afterSeq });
      const events = result.data?.events ?? [];
      for (const event of events) { apply(event); afterSeq = Math.max(afterSeq, event.seq); }
      const state = result.data?.state ?? run.state;
      run = { ...run, state };
      for (const [, q] of pendingFromEvents(events)) {
        if (!answered.has(q.questionId) && !list.querySelector(`[data-question="${CSS.escape(String(q.questionId))}"]`)) {
          typing.before(approvalCard(q, rpc, () => { onChange(); poll(); }));
        }
      }
      typing.hidden = !["queued", "running"].includes(state);
      if (events.length) scrollEnd();
      if (ACTIVE_STATES.includes(state)) timer = setTimeout(poll, POLL_MS);
    } catch (error) {
      if (error.auth) { open = false; return onChange(true); }
      timer = setTimeout(poll, POLL_MS * 2); // ağ kopması: sohbet açık kaldıkça tekrar dener
    }
  }

  async function submit() {
    const text = input.value.trim();
    if (!text) return;
    input.value = "";
    input.rows = 1;
    const result = await rpc("tasks.create", { prompt: text, idempotencyKey: crypto.randomUUID() });
    if (!result.ok) return bubble("error", result.message || "Gönderilemedi.");
    onCreated(result.data);
  }

  function close() { open = false; clearTimeout(timer); }

  return {
    show(task) {
      close();
      run = task ? { ...task } : null;
      afterSeq = 0;
      answered.clear();
      for (const node of [...list.children]) if (node !== typing) node.remove();
      typing.hidden = true;
      title.textContent = task ? "Sohbet" : "Yeni sohbet";
      if (task) bubble("user", task.summary);
      open = true;
      void poll();
      if (!task) input.focus();
    },
    close,
  };
}

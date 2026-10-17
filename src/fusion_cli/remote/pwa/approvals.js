import { h } from "./dom.js";

// Görevin olay akışından hâlâ yanıt bekleyen onayları çıkarır.
export function pendingFromEvents(events) {
  const pending = new Map();
  for (const event of events) {
    if (event.kind === "approval_request") pending.set(event.payload.questionId, event.payload);
    if (event.kind === "approval_answered") pending.delete(event.payload.questionId);
  }
  return pending;
}

export function approvalCard(question, rpc, after) {
  const answer = async (choice) => {
    await rpc("approvals.respond", { questionId: question.questionId, choice });
    after();
  };
  const buttons = [];
  if (!question.stepUp) buttons.push(h("button", { class: "btn", type: "button", onclick: () => answer("once") }, "Bir kez izin ver"));
  buttons.push(h("button", { class: "btn ghost", type: "button", onclick: () => answer("deny") }, "Reddet"));
  return h(
    "div",
    { class: "approval", "data-question": question.questionId },
    h("div", { class: "approval-title" }, question.title || "Onay gerekiyor"),
    question.target ? h("div", { class: "muted mono" }, question.target) : null,
    question.stepUp ? h("div", { class: "danger" }, "Bu işlem güvenlik nedeniyle yalnız masaüstünde onaylanır.") : null,
    h("div", { class: "row" }, buttons),
  );
}

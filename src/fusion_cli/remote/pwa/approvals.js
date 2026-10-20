import { h } from "./dom.js";

// Aynı açık soru iki görünümde de tek karar kimliğiyle yanıtlanır.
const decisions = new Map();
function decisionId(questionId, choice) {
  const key = `${questionId}:${choice}`;
  if (!decisions.has(key)) decisions.set(key, crypto.randomUUID());
  return decisions.get(key);
}

export function pendingFromEvents(events) {
  const pending = new Map();
  for (const event of events) {
    if (event.kind === "approval_request") pending.set(event.payload.questionId, event.payload);
    if (event.kind === "approval_answered") pending.delete(event.payload.questionId);
  }
  return pending;
}

export function approvalCard(question, rpc, after) {
  const error = h("p", { class: "approval-error danger", role: "alert", hidden: true });
  const receipt = h("p", { class: "muted small", role: "status", hidden: true });
  const actions = h("div", { class: "approval-actions" });
  const confirmation = h("div", { class: "approval-confirm", hidden: true });
  const card = h("section", { class: "approval", "data-question": question.questionId },
    h("span", { class: "approval-eyebrow" }, "İzin gerekiyor"),
    h("h3", { class: "approval-title" }, question.title || "İşlemi onayla"),
    question.target ? h("pre", { class: "approval-target mono" }, question.target) : null,
    question.reason || question.danger ? h("p", { class: "muted small" }, question.danger || question.reason) : null,
    actions, confirmation, receipt, error);
  if (question.args?.length || question.diff) {
    const details = h("details", { class: "approval-details" }, h("summary", {}, "İşlem ayrıntıları"));
    if (question.args?.length) details.append(h("pre", { class: "mono" }, typeof question.args === "string" ? question.args : JSON.stringify(question.args, null, 2)));
    if (question.diff) details.append(h("pre", { class: "mono" }, typeof question.diff === "string" ? question.diff : JSON.stringify(question.diff, null, 2)));
    card.insertBefore(details, actions);
  }
  let busy = false;
  function setBusy(value) {
    busy = value;
    for (const button of card.querySelectorAll("button")) button.disabled = value;
    receipt.hidden = !value;
    receipt.textContent = value ? "Kararın iletiliyor…" : "";
  }
  async function answer(choice, confirmed = false) {
    if (busy) return;
    if (choice !== "deny" && (question.stepUp || choice === "session") && !confirmed) {
      confirmation.replaceChildren(
        h("p", {}, "Bu işlemi bilgisayarında gerçekleştirmesine izin veriyor musun?"),
        h("button", { class: "btn", type: "button", onclick: () => answer(choice, true) }, "İşlemi onayla"),
        h("button", { class: "btn ghost", type: "button", onclick: () => { confirmation.hidden = true; actions.hidden = false; } }, "Vazgeç"));
      actions.hidden = true;
      confirmation.hidden = false;
      confirmation.querySelector("button").focus();
      return;
    }
    setBusy(true);
    error.hidden = true;
    try {
      const params = { questionId: question.questionId, choice, decisionId: decisionId(question.questionId, choice) };
      if (confirmed) {
        const challenge = await rpc("approvals.challenge", { questionId: question.questionId, choice });
        if (!challenge.ok || !challenge.data?.challengeId) throw new Error(challenge.message || "İşlem teyidi alınamadı. Tekrar dene.");
        params.confirmation = challenge.data.challengeId;
      }
      const result = await rpc("approvals.respond", params);
      if (!result.ok || result.data?.accepted !== true) throw new Error(result.message || "Onay göreve ulaşmadı. Tekrar dene.");
      receipt.hidden = false;
      receipt.textContent = choice === "deny" ? "İşlem reddedildi." : "Onay alındı; görev sürüyor.";
      card.dataset.resolved = "true";
      await after();
    } catch (failure) {
      setBusy(false);
      error.textContent = failure.message || "Karar iletilemedi. Bağlantını kontrol edip tekrar dene.";
      error.hidden = false;
    }
  }
  const labels = { once: "Bir kez izin ver", session: "Bu oturumda izin ver", deny: "Reddet" };
  const offered = (question.options?.length ? question.options : ["once", "deny"]).map((item) => typeof item === "string" ? item : item.deger);
  for (const choice of offered) {
    if (!labels[choice]) continue;
    actions.append(h("button", { class: `btn ${choice === "deny" ? "ghost" : ""}`, type: "button", onclick: () => answer(choice) }, labels[choice]));
  }
  return card;
}

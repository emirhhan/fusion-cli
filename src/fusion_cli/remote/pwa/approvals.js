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

// `args` metin, dizi ya da nesne gelebilir; `.length` yalnız ilk ikisinde vardır (nesne ayrıntısı gizlenmesin).
function hasContent(value) {
  if (value === null || value === undefined) return false;
  if (typeof value === "string" || Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

// `scopes`: cihazın eşleşme kapsamları. Onayın gerektirdiği kapsam yoksa sunucu yalnız
// reddi kabul eder; kart boşuna onay düğmesi göstermez, masaüstüne yönlendirir.
// `authority`: `service.status.approvalAuthority` — masaüstü cihaz başına süreli onay yetkisi
// istiyorsa ve bu cihazda yoksa (P-040) yine yalnız Reddet sunulur.
export function approvalCard(question, rpc, after, scopes = null, authority = null) {
  const error = h("p", { class: "approval-error danger", role: "alert", hidden: true });
  const receipt = h("p", { class: "muted small", role: "status", hidden: true });
  const actions = h("div", { class: "approval-actions" });
  const confirmation = h("div", { class: "approval-confirm", hidden: true });
  const card = h("section", { class: "approval", "data-question": question.questionId },
    h("span", { class: "approval-eyebrow" }, "İzin gerekiyor"),
    h("h3", { class: "approval-title" }, question.title || "İşlemi onayla"),
    question.target ? h("pre", { class: "approval-target mono" }, question.target) : null,
    question.danger ? h("p", { class: "approval-danger danger small" }, question.danger) : null,
    question.reason ? h("p", { class: "muted small" }, question.reason) : null,
    actions, confirmation, receipt, error);
  if (hasContent(question.args) || question.diff) {
    const details = h("details", { class: "approval-details" }, h("summary", {}, "İşlem ayrıntıları"));
    if (hasContent(question.args)) details.append(h("pre", { class: "mono" }, typeof question.args === "string" ? question.args : JSON.stringify(question.args, null, 2)));
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
  const scopeAllowed = !question.requiredScope || !Array.isArray(scopes) || scopes.includes(question.requiredScope);
  const trusted = !(authority && authority.required === true && authority.canApprove !== true);
  const allowed = scopeAllowed && trusted;
  if (!scopeAllowed) {
    card.insertBefore(h("p", { class: "muted small approval-desktop-only" },
      `Bu onayı bu telefondan veremezsin ('${question.requiredScope}' yetkisi yok). Bilgisayardan onayla ya da burada reddet.`), actions);
  } else if (!trusted) {
    card.insertBefore(h("p", { class: "muted small approval-desktop-only" },
      "Bu telefona uzaktan onay yetkisi verilmemiş ya da süresi dolmuş. Bilgisayarda Ayarlar › Uzaktan Erişim'den yetki ver ya da burada reddet."), actions);
  }
  const shown = offered.filter((choice) => labels[choice] && (allowed || choice === "deny"));
  // Tanınmayan seçenekler kartı düğmesiz bırakıp görevi sonsuza dek bekletmesin: Reddet daima vardır.
  if (!offered.some((choice) => labels[choice])) {
    card.insertBefore(h("p", { class: "muted small approval-desktop-only" }, "Bu onayın seçenekleri bu uygulamada tanınmıyor. Bilgisayardan onayla ya da burada reddet."), actions);
  }
  if (!shown.includes("deny")) shown.push("deny");
  for (const choice of shown) {
    actions.append(h("button", { class: `btn ${choice === "deny" ? "ghost" : ""}`, type: "button", onclick: () => answer(choice) }, labels[choice]));
  }
  return card;
}

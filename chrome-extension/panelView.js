// Yan panelin çizimi: mesajlar, canlı adımlar, izin/soru kartı.
// Hiçbir yerde innerHTML kullanılmaz: model ve sayfa metni yalnız textContent ile yazılır.

const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

/** `**kalın**` ve `kod` parçalarını düğüm olarak ekler. */
function appendInline(parent, text) {
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) parent.append(text.slice(last, match.index));
    const token = match[0];
    parent.append(token.startsWith("**") ? el("strong", "", token.slice(2, -2)) : el("code", "", token.slice(1, -1)));
    last = match.index + token.length;
  }
  if (last < text.length) parent.append(text.slice(last));
}

/** Modelin kısa Markdown'ını güvenli düğümlere çevirir: başlık, liste, kod, paragraf. */
export function renderMarkdown(text) {
  const root = el("div", "prose");
  let list = null;
  let code = null;
  for (const raw of String(text || "").split("\n")) {
    const line = raw.trimEnd();
    if (line.startsWith("```")) {
      if (code) { root.append(code); code = null; } else { code = el("pre"); code.append(el("code")); }
      list = null;
      continue;
    }
    if (code) { code.firstChild.textContent += `${raw}\n`; continue; }
    const bullet = /^\s*(?:[-*•]|\d+[.)])\s+(.*)$/.exec(line);
    if (bullet) {
      const ordered = /^\s*\d/.test(line);
      if (!list || (list.tagName === "OL") !== ordered) { list = el(ordered ? "ol" : "ul"); root.append(list); }
      const item = el("li");
      appendInline(item, bullet[1]);
      list.append(item);
      continue;
    }
    list = null;
    if (!line.trim()) continue;
    const heading = /^#{1,6}\s+(.*)$/.exec(line);
    const block = el(heading ? "h4" : "p");
    appendInline(block, heading ? heading[1] : line);
    root.append(block);
  }
  if (code) root.append(code);
  return root;
}

const STEP_ICONS = {
  chrome_navigate: "M3 10h14M10 3c2.5 2.2 2.5 11.8 0 14M10 3c-2.5 2.2-2.5 11.8 0 14",
  chrome_page: "M4 4.5h12M4 8.5h12M4 12.5h8",
  chrome_click: "M7 3.5v6l2-1.5 1.7 4 1.6-.7-1.7-4 2.6-.3z",
  chrome_type: "M4 6h12M10 6v9",
  chrome_action: "M10 4v12M6 12l4 4 4-4",
};

function stepRow(step) {
  const row = el("li", "step");
  row.dataset.state = step.durum || "ok";
  const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  icon.setAttribute("viewBox", "0 0 20 20");
  icon.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", STEP_ICONS[step.arac] || STEP_ICONS.chrome_page);
  icon.append(path);
  const text = el("span", "step__text", step.metin);
  row.append(icon, text);
  if (step.durum === "failed" && step.hata) row.append(el("span", "step__error", step.hata));
  if (step.durum === "denied" || step.durum === "blocked") row.append(el("span", "step__error", "İzin verilmedi"));
  return row;
}

function stepsBlock(message) {
  const steps = message.adimlar || [];
  const running = message.durum === "calisiyor";
  if (!steps.length && !running) return null;
  const details = el("details", "steps");
  details.open = running || steps.length <= 3;
  const summary = el("summary", "steps__summary");
  const count = steps.length ? `${steps.length} adım` : "";
  summary.append(el("span", running ? "steps__live" : "", running ? message.etiket || "Çalışıyor…" : count));
  if (running && count) summary.append(el("span", "steps__count", count));
  details.append(summary);
  const list = el("ol", "steps__list");
  steps.forEach((step) => list.append(stepRow(step)));
  details.append(list);
  return details;
}

/** Tek mesajı liste öğesi olarak çizer. */
export function renderMessage(message) {
  const item = el("li", `message message--${message.rol}`);
  if (message.rol === "kullanici") {
    item.append(el("div", "bubble", message.metin));
    return item;
  }
  item.dataset.state = message.durum || "bitti";
  const steps = stepsBlock(message);
  if (steps) item.append(steps);
  if (message.metin) item.append(renderMarkdown(message.metin));
  if (message.durum === "iptal") item.append(el("p", "message__note", "Durduruldu."));
  return item;
}

/**
 * İzin ya da soru kartı. `onAnswer` çekirdeğin beklediği veriyle çağrılır:
 * onayda `{secim}`, soruda `{metin}`. 1-9 tuşları seçer, Esc reddeder/atlar.
 */
export function renderAsk(container, question, onAnswer) {
  container.replaceChildren();
  const data = question.veri || {};
  const isQuestion = data.tur === "soru";
  container.dataset.kind = isQuestion ? "soru" : "onay";
  container.append(el("div", "ask__eyebrow", isQuestion ? "Fusion soruyor" : "İzin gerekiyor"));
  const title = el("h2", "ask__title", isQuestion ? data.soru || "Fusion bir şey soruyor" : data.baslik || "Bu işlem yapılsın mı?");
  title.id = "ask-title";
  container.append(title);
  if (!isQuestion && data.hedef) container.append(el("pre", "ask__target", String(data.hedef)));
  if (data.tehlike) container.append(el("p", "ask__danger", `Dikkat: ${data.tehlike}`));
  const options = (data.secenekler || []).map((option) => isQuestion
    ? { label: option.etiket, hint: option.aciklama, answer: { metin: option.etiket }, deny: false }
    : { label: option.etiket, answer: { secim: option.deger }, deny: option.deger === "deny" });
  const group = el("div", "ask__options");
  options.forEach((option, index) => {
    const button = el("button", "ask__option");
    button.type = "button";
    if (option.deny) button.dataset.deny = "true";
    button.append(el("kbd", "", String(index + 1)));
    const label = el("span", "ask__label", option.label);
    if (option.hint) label.append(el("small", "", option.hint));
    button.append(label);
    button.addEventListener("click", () => onAnswer(option.answer));
    group.append(button);
  });
  container.append(group);
  if (isQuestion) {
    const form = el("form", "ask__other");
    const input = el("input");
    input.placeholder = "Kendi cevabını yaz…";
    input.setAttribute("aria-label", "Cevabın");
    const submit = el("button", "", "Gönder");
    submit.type = "submit";
    form.append(input, submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (input.value.trim()) onAnswer({ metin: input.value.trim() });
    });
    container.append(form);
  }
  container.append(el("p", "ask__hint", isQuestion ? "Sayıyla seç · Esc soruyu atla" : "Sayıyla seç · Esc reddet"));
  container.onkeydown = (event) => {
    if (event.target instanceof HTMLInputElement) return;
    if (event.key === "Escape") {
      event.preventDefault();
      const deny = options.find((option) => option.deny);
      onAnswer(isQuestion ? { metin: "" } : deny ? deny.answer : { secim: "deny" });
      return;
    }
    const index = Number(event.key) - 1;
    if (Number.isInteger(index) && options[index]) {
      event.preventDefault();
      onAnswer(options[index].answer);
    }
  };
  container.hidden = false;
  container.focus();
}

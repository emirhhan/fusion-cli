import { h } from "./dom.js";

export function renderSettings(ctx, root, { selectTier, renameProject, deleteProject, unpair }) {
  const nodes = [h("p", { class: "muted small" }, ctx.notice || "")];

  nodes.push(h("h2", { class: "group" }, "Model"));
  if (!ctx.tiers.length) nodes.push(h("p", { class: "muted small" }, "Model listesi alınamadı."));
  else {
    const select = h("select", { class: "pick wide", "aria-label": "Model" },
      ...ctx.tiers.map((t) => h("option", { value: t.name }, `${t.label}${t.model ? ` · ${t.model}` : ""}`)));
    select.value = ctx.tier || ctx.activeTier || "";
    select.addEventListener("change", () => selectTier(select.value));
    nodes.push(select, h("p", { class: "muted small" }, ctx.tiersEditable ? "Seçim sonraki mesajlardan itibaren geçerli olur." : "Model değişikliği masaüstünde kilitli."));
  }

  nodes.push(h("h2", { class: "group" }, "Projeler"));
  if (!ctx.projects.length) nodes.push(h("p", { class: "muted small" }, "Henüz proje yok. Sohbetler sekmesinden ekleyebilirsin."));
  for (const project of ctx.projects) {
    nodes.push(h("div", { class: "card-row" },
      h("div", { class: "row-main" }, h("span", { class: "row-title" }, project.name),
        h("span", { class: "row-sub" }, project.hasFolder ? "Klasörlü (masaüstünden)" : "Klasörsüz")),
      h("button", { class: "btn ghost small", type: "button", onclick: () => renameProject(project) }, "Adı değiştir"),
      h("button", { class: "btn ghost small danger", type: "button", onclick: () => deleteProject(project) }, "Sil")));
  }
  nodes.push(h("button", { class: "btn ghost danger-btn", type: "button", onclick: unpair }, "Bu cihazın eşleşmesini kaldır"));
  root.replaceChildren(...nodes);
}

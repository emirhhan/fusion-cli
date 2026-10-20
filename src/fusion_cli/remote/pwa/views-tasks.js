import { ACTIVE_STATES, STATE_LABEL, h, timeAgo } from "./dom.js";

const taskRow = (task, open) => h("button", { class: "row-item", type: "button", onclick: () => open(task) },
  h("span", { class: "row-main" }, h("span", { class: "row-title" }, task.summary || "(boş)"), h("span", { class: "row-sub" }, STATE_LABEL[task.state] ?? task.state)),
  h("span", { class: "row-time muted" }, timeAgo(task.createdAt)));

export function renderTasks(ctx, root, { open, cancel, runSchedule, toggleSchedule, runKit }) {
  const nodes = [];
  const group = (name, items, cancellable) => {
    if (!items.length) return;
    nodes.push(h("h2", { class: "group" }, name));
    for (const task of items) {
      nodes.push(h("div", { class: "task" }, taskRow(task, open),
        cancellable ? h("button", { class: "btn ghost small", type: "button", onclick: () => cancel(task) }, "Durdur") : null));
    }
  };
  group("Çalışan", ctx.tasks.filter((t) => ACTIVE_STATES.includes(t.state)), true);
  group("Biten", ctx.tasks.filter((t) => !ACTIVE_STATES.includes(t.state)), false);

  nodes.push(h("h2", { class: "group" }, "Zamanlananlar"));
  if (ctx.schedules === null) nodes.push(h("p", { class: "muted small" }, "Zamanlananlar şu an okunamadı."));
  else if (!ctx.schedules.length) nodes.push(h("p", { class: "muted small" }, "Zamanlanan görev yok. Masaüstü Fusion'dan eklenir."));
  for (const item of ctx.schedules ?? []) {
    nodes.push(h("div", { class: "card-row" },
      h("div", { class: "row-main" }, h("span", { class: "row-title" }, item.title),
        h("span", { class: "row-sub" }, item.enabled ? (item.next ? `Sıradaki: ${new Date(item.next * 1000).toLocaleString("tr-TR")}` : "Sıradaki yok") : "Duraklatıldı")),
      h("button", { class: "btn ghost small", type: "button", onclick: () => toggleSchedule(item) }, item.enabled ? "Duraklat" : "Sürdür"),
      h("button", { class: "btn small", type: "button", onclick: () => runSchedule(item) }, "Şimdi çalıştır")));
  }

  if (ctx.scopes.includes("kits.list")) {
    nodes.push(h("h2", { class: "group" }, "Kits"));
    if (!ctx.kits.length) nodes.push(h("p", { class: "muted small" }, "Uzaktan çalıştırmaya açık kit yok. Bir kit masaüstünde uzaktan erişime açılmalı."));
    for (const kit of ctx.kits) {
      nodes.push(h("div", { class: "card-row" }, h("div", { class: "row-main" }, h("span", { class: "row-title" }, kit.title)),
        h("button", { class: "btn small", type: "button", onclick: () => runKit(kit) }, "Çalıştır")));
    }
  }
  root.replaceChildren(...nodes);
}

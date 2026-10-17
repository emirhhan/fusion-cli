import { ACTIVE_STATES, STATE_LABEL, h, icon, timeAgo } from "./dom.js";

// Sohbet satırları: diskteki sohbetler + henüz diske yazılmamış canlı görevler + eski (sohbetsiz) görevler.
export function chatRows(ctx) {
  const latest = new Map();
  for (const task of ctx.tasks) {
    const key = task.chatId || task.runId;
    if (!latest.has(key) || latest.get(key).createdAt < task.createdAt) latest.set(key, task);
  }
  const rows = ctx.chats.map((c) => ({
    chatId: c.id, root: c.root, projectId: c.projectId, title: c.title || "Sohbet",
    updatedAt: c.updatedAt, task: latest.get(c.id) ?? null,
  }));
  const known = new Set(ctx.chats.map((c) => c.id));
  for (const [key, task] of latest) {
    if (known.has(key)) continue;
    const chatId = task.chatId || "";
    rows.push({
      chatId, root: undefined, projectId: ctx.chatProjects[chatId] ?? null,
      title: task.summary, updatedAt: task.createdAt, task,
    });
  }
  return rows.sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0));
}

export function filterRows(rows, filter) {
  if (filter === "all") return rows;
  if (filter === "none") return rows.filter((r) => !r.projectId);
  return rows.filter((r) => r.projectId === filter);
}

export function renderChats(ctx, root, { open, onProjectCreate }) {
  const chips = h("div", { class: "chips scroll", role: "tablist", "aria-label": "Proje süzgeci" });
  const chip = (id, label) => h("button", {
    class: `chip-btn ${ctx.filter === id ? "on" : ""}`, type: "button", role: "tab",
    "aria-selected": String(ctx.filter === id),
    onclick: () => { ctx.filter = id; renderChats(ctx, root, { open, onProjectCreate }); },
  }, label);
  chips.append(chip("all", "Tümü"), chip("none", "Projesiz"), ...ctx.projects.map((p) => chip(p.id, p.name)));
  const nameInput = h("input", { type: "text", maxlength: "80", placeholder: "Yeni proje adı", "aria-label": "Yeni proje adı" });
  const form = h("form", { class: "inline-form", hidden: true },
    nameInput, h("button", { class: "btn small", type: "submit" }, "Ekle"));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (await onProjectCreate(nameInput.value)) { nameInput.value = ""; form.hidden = true; }
  });
  const add = h("button", { class: "chip-btn", type: "button", "aria-label": "Proje ekle", onclick: () => { form.hidden = !form.hidden; nameInput.focus(); } }, icon("folder"), " +");
  chips.append(add);

  const rows = filterRows(chatRows(ctx), ctx.filter);
  const projectName = (id) => ctx.projects.find((p) => p.id === id)?.name;
  const items = rows.map((row) => {
    const active = row.task && ACTIVE_STATES.includes(row.task.state);
    const sub = [projectName(row.projectId), active ? STATE_LABEL[row.task.state] : null].filter(Boolean).join(" · ");
    return h("button", { class: "row-item", type: "button", onclick: () => open(row) },
      h("span", { class: `avatar ${active ? "live" : ""}` }, icon("chat")),
      h("span", { class: "row-main" }, h("span", { class: "row-title" }, row.title), sub ? h("span", { class: "row-sub" }, sub) : null),
      h("span", { class: "row-time muted" }, row.updatedAt ? timeAgo(row.updatedAt) : ""));
  });
  root.replaceChildren(chips, form, ...(items.length ? items : [h("p", { class: "empty" }, "Bu görünümde sohbet yok. Sağ üstteki + ile başla.")]));
}

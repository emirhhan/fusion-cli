// A site grant never expands the authority of an accepted current-tab task.
export const TASK_SCOPE_VERSION = 1;
const READS = new Set([
  "tabs", "find", "snapshot", "assets", "text_page", "describe", "describe_key",
  "describe_at", "tree", "console", "network", "wait", "text", "design",
]);
function blocked() {
  const error = new Error("Bu görev yalnız başlangıçtaki sekme ve site için yetkili; istenen işlem engellendi.");
  error.code = "task_scope";
  return error;
}
function origin(value) {
  try {
    const url = new URL(value);
    return /^https?:$/.test(url.protocol) && !url.username && !url.password ? url.origin : null;
  } catch { return null; }
}

/** Run before every permission lookup or action; never use mutable selected-tab state. */
export async function taskScopedTab(command) {
  if (!("taskScope" in command)) return null;
  const scope = command.taskScope;
  if (!scope || scope.version !== TASK_SCOPE_VERSION || !Number.isSafeInteger(scope.tabId) || scope.tabId <= 0 ||
      origin(scope.origin) !== scope.origin) throw blocked();
  const args = command.veri || {};
  if ("tabId" in args && args.tabId !== scope.tabId) throw blocked();
  const allowed = READS.has(command.islem) ||
    command.islem === "navigate" && origin(args.url) === scope.origin ||
    command.islem === "tab_select" && args.id === scope.tabId ||
    command.islem === "history" && args.dir === "reload";
  // Click/key/script/history can navigate indirectly; they require a new user task.
  if (!allowed) throw blocked();
  const tab = await chrome.tabs.get(scope.tabId).catch(() => null);
  if (!tab || origin(tab.url) !== scope.origin || tab.pendingUrl && origin(tab.pendingUrl) !== scope.origin) throw blocked();
  return tab;
}

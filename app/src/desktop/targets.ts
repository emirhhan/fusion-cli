export type DesktopTarget = { kind: "window"; id: number; pid: number } | { kind: "tab"; id: number };
export interface DockItem { target: DesktopTarget; title: string; icon?: string }
export interface DesktopActivity { key: string; target: Extract<DesktopTarget, { kind: "window" }>; label: string }

function record(value: unknown): value is Record<string, unknown> { return typeof value === "object" && value !== null; }
function positive(value: unknown): value is number { return typeof value === "number" && Number.isInteger(value) && value > 0; }
export function parseTarget(value: unknown): DesktopTarget | null {
  if (!record(value) || !positive(value.id)) return null;
  if (value.kind === "window" && positive(value.pid)) return { kind: "window", id: value.id, pid: value.pid };
  return value.kind === "tab" ? { kind: "tab", id: value.id } : null;
}
export function parseItems(value: unknown): DockItem[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item: unknown) => {
    if (!record(item)) return [];
    const target = parseTarget(item);
    if (!target) return [];
    const title = typeof item.title === "string" && item.title ? item.title : "Başlıksız";
    const app = target.kind === "window" && typeof item.app === "string" ? item.app : "";
    return [{ target, title: app ? `${app}: ${title}` : title,
      icon: typeof item.icon === "string" && /^data:image\/png;base64,[A-Za-z0-9+/]+=*$/.test(item.icon) ? item.icon : undefined }];
  });
}
export function parseActivity(value: Record<string, unknown>): DesktopActivity | null {
  const target = parseTarget(value.target);
  if (value.ok !== true || value.active !== true || target?.kind !== "window"
    || typeof value.activityId !== "string" || !value.activityId) return null;
  return { key: value.activityId, target, label: typeof value.label === "string" ? value.label : "Pencerede çalışıyor" };
}

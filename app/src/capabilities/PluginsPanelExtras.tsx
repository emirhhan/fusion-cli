/**
 * Eklenti panelinin Claude Code `/plugin` eşdeğer parçaları (#382, #394, #397, #399, #401):
 * kurulum kapsamı seçici, oturumluk / skills-dir eklentileri, "Flagged" (pazardan kaldırılan)
 * eklentiler ve pazarın bildirdiği komut (command kaynağı / headersHelper) için onay kartı.
 */

export type InstallScope = "user" | "project" | "local";

export interface SessionPlugin { kimlik: string; ad: string; kapsam: string; surum: string; aciklama: string; etkin: boolean }
export interface FlaggedPlugin { kimlik: string; tarih: string }
export interface ShownCommand { kind: string; pluginId: string; command: string; sha256: string; mode?: string; archiveUrl?: string }

const SCOPE_LABEL: Record<InstallScope, string> = {
  user: "Senin için (user)",
  project: "Bu depodaki herkes için (project)",
  local: "Yalnız senin için, bu depoda (local)",
};

function record(raw: unknown): Record<string, unknown> | null {
  return raw && typeof raw === "object" ? (raw as Record<string, unknown>) : null;
}

function text(raw: unknown): string {
  return typeof raw === "string" ? raw : "";
}

export function sessionFrom(raw: unknown): SessionPlugin[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(record).filter((item): item is Record<string, unknown> => item !== null && typeof item.kimlik === "string").map((item) => ({
    kimlik: text(item.kimlik), ad: text(item.ad), kapsam: text(item.kapsam), surum: text(item.surum), aciklama: text(item.aciklama), etkin: item.etkin !== false,
  }));
}

export function flaggedFrom(raw: unknown): FlaggedPlugin[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(record).filter((item): item is Record<string, unknown> => item !== null && typeof item.kimlik === "string").map((item) => ({ kimlik: text(item.kimlik), tarih: text(item.tarih) }));
}

export function shownCommandFrom(raw: unknown): ShownCommand | null {
  const item = record(raw);
  if (!item || typeof item.sha256 !== "string" || typeof item.command !== "string") return null;
  return { kind: text(item.kind), pluginId: text(item.pluginId), command: item.command, sha256: item.sha256, mode: text(item.mode), archiveUrl: text(item.archiveUrl) };
}

export function ScopeSelect({ value, onChange, disabled }: { value: InstallScope; onChange: (scope: InstallScope) => void; disabled: boolean }) {
  return (
    <select aria-label="Kurulum kapsamı" disabled={disabled} onChange={(event) => onChange(event.target.value as InstallScope)} value={value}>
      {(Object.keys(SCOPE_LABEL) as InstallScope[]).map((scope) => <option key={scope} value={scope}>{SCOPE_LABEL[scope]}</option>)}
    </select>
  );
}

const SESSION_LABEL: Record<string, string> = { session: "oturumluk (--plugin-dir / --plugin-url)", "skills-dir": "skills-dir (~/.claude/skills)" };

export function SessionPlugins({ items }: { items: SessionPlugin[] }) {
  if (items.length === 0) return null;
  return (
    <ul aria-label="Kurulmadan yüklenen eklentiler" className="plugins-panel__list">
      {items.map((item) => (
        <li className="plugins-panel__item" data-status={item.etkin ? "on" : "off"} key={item.kimlik}>
          <div className="plugins-panel__text">
            <strong>{item.kimlik}{item.surum ? ` ${item.surum}` : ""}</strong>
            {item.aciklama && <span>{item.aciklama}</span>}
            <small>{SESSION_LABEL[item.kapsam] ?? item.kapsam} · {item.etkin ? "etkin" : "kapalı"}</small>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function FlaggedPlugins({ items }: { items: FlaggedPlugin[] }) {
  if (items.length === 0) return null;
  return (
    <ul aria-label="Pazardan kaldırılan eklentiler" className="plugins-panel__list">
      {items.map((item) => (
        <li className="plugins-panel__item" data-status="warn" key={item.kimlik}>
          <div className="plugins-panel__text">
            <strong>{item.kimlik}</strong>
            <small>Flagged · Removed from marketplace · {item.tarih}</small>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function CommandCard({ shown, busy, onConfirm, onCancel }: { shown: ShownCommand; busy: boolean; onConfirm: () => void; onCancel: () => void }) {
  const what = shown.kind === "command_source" ? `eklenti kaynağı (${shown.mode || "copy"})` : `arşiv başlıkları (${shown.archiveUrl ?? ""})`;
  return (
    <section aria-label="Pazar komutu onayı" className="plugins-panel__preview">
      <h3>{shown.pluginId}</h3>
      <p className="plugins-panel__warn" role="note">Pazar bu eklenti için yerel bir komut çalıştıracak: {what}. Komut senin kullanıcınla, ev klasöründen çalışır; yalnız güvendiğin pazarlarda onayla.</p>
      <pre><code>{shown.command}</code></pre>
      <div className="plugins-panel__actions">
        <button className="plugins-panel__primary" disabled={busy} onClick={onConfirm} type="button">Komutu onayla ve sürdür</button>
        <button disabled={busy} onClick={onCancel} type="button">Vazgeç</button>
      </div>
    </section>
  );
}

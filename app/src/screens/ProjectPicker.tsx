import { useEffect, useRef, useState } from "react";
import type { RecentProject } from "../sessions/types";
import { projectName } from "../sessions/projectRoots";
import { Icon } from "../ui/Icon";
import "./ProjectPicker.css";
export function ProjectPicker({ root, projects, onSelect, onNew, onSettings }: { root: string; projects: RecentProject[]; onSelect: (root: string) => Promise<void>; onNew: () => void; onSettings: () => void }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => { if (!ref.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { setOpen(false); triggerRef.current?.focus(); } };
    document.addEventListener("mousedown", outside); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", outside); document.removeEventListener("keydown", escape); };
  }, [open]);
  const choices = [{ root, name: projectName(root) }, ...projects.filter((project) => project.root !== root)].filter((project) => `${project.name} ${project.root}`.toLocaleLowerCase("tr").includes(query.toLocaleLowerCase("tr")));
  return <div className="project-picker" ref={ref}>
    <button ref={triggerRef} aria-expanded={open} aria-label={`Proje seç: ${projectName(root)}`} className="project-picker__trigger" onClick={() => setOpen((current) => !current)} type="button"><Icon name="folder" size={18} />{projectName(root)}<Icon name="chevron" size={14} /></button>
    {open && <div aria-label="Proje seçimi" className="project-picker__menu">
      <label className="project-picker__search"><Icon name="search" size={18} /><input aria-label="Proje ara" autoFocus onChange={(event) => setQuery(event.target.value)} placeholder="Proje ara" value={query} /></label>
      <div className="project-picker__choices">{choices.map((project) => <button aria-pressed={project.root === root} disabled={busy} key={project.root} onClick={() => { if (project.root === root) { setOpen(false); triggerRef.current?.focus(); return; } setBusy(true); setError(null); void onSelect(project.root).then(() => { setOpen(false); triggerRef.current?.focus(); }).catch(() => setError("Proje açılamadı. Yeniden dene.")).finally(() => setBusy(false)); }} title={project.root} type="button"><Icon name="folder" size={18} /><span>{project.name}</span>{project.root === root && <span aria-hidden="true">✓</span>}</button>)}</div>
      {choices.length === 0 && <p>Proje bulunamadı.</p>}{error && <p role="alert">{error}</p>}
      <div className="project-picker__divider" />
      <button disabled={busy} onClick={() => { setOpen(false); onNew(); }} type="button"><Icon name="new" size={18} />Yeni proje / klasör seç</button>
      <button disabled={busy} onClick={() => { setOpen(false); onSettings(); }} type="button"><Icon name="settings" size={18} />Proje ayarları</button>
    </div>}
  </div>;
}

import { useMemo, useState } from "react";
import { Icon, type IconName } from "../ui/Icon";
import "./Sidebar.css";

export interface OturumSatiri {
  session_id: string;
  source: string;
  title: string;
}

type HistorySource = "fusion" | "claude" | "codex" | "hermes";

interface SidebarProps {
  availableSources?: HistorySource[];
  collapsed?: boolean;
  etkin: string | null;
  onNavigate?: (destination: string) => void;
  onSec: (id: string) => void;
  onYeni: () => void;
  oturumlar: OturumSatiri[];
}

interface NavItemProps {
  icon: IconName;
  label: string;
  onClick?: () => void;
}

function NavItem({ icon, label, onClick }: NavItemProps) {
  return (
    <button aria-label={label} className="sidebar__nav-item" onClick={onClick} type="button">
      <Icon name={icon} size={18} />
      <span className="sidebar__label">{label}</span>
    </button>
  );
}

function SessionButton({ session, active, onSelect }: {
  session: OturumSatiri;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className="sidebar__session"
      data-etkin={active}
      onClick={onSelect}
      type="button"
    >
      <span className="sidebar__session-title">{session.title}</span>
      <span className="sidebar__session-source">[{session.source}]</span>
    </button>
  );
}

export function Sidebar({
  availableSources = [],
  collapsed = false,
  etkin,
  onNavigate = () => undefined,
  onSec,
  onYeni,
  oturumlar,
}: SidebarProps) {
  const [query, setQuery] = useState("");
  const filteredSessions = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("tr");
    if (!normalized) return oturumlar;
    return oturumlar.filter((session) =>
      `${session.title} ${session.source}`.toLocaleLowerCase("tr").includes(normalized),
    );
  }, [oturumlar, query]);

  return (
    <nav aria-label="Fusion" className="sidebar" data-collapsed={collapsed}>
      <div className="sidebar__top">
        <div aria-label="Fusion" className="sidebar__brand">
          <span className="sidebar__brand-mark" aria-hidden="true">F</span>
          <span className="sidebar__label">Fusion</span>
        </div>
        <NavItem icon="new" label="Yeni görev" onClick={onYeni} />
        <label className="sidebar__search">
          <Icon name="search" size={17} />
          <span className="sidebar__sr-only">Konuşma ve proje ara</span>
          <input
            aria-label="Konuşma ve proje ara"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ara"
            type="search"
            value={query}
          />
        </label>
      </div>

      <div className="sidebar__scroll">
        {filteredSessions.length > 0 && (
          <section aria-labelledby="recent-sessions-title" className="sidebar__section">
            <h2 id="recent-sessions-title" className="sidebar__section-title">Sohbetler</h2>
            {filteredSessions.map((session) => (
              <SessionButton
                active={session.session_id === etkin}
                key={session.session_id}
                onSelect={() => onSec(session.session_id)}
                session={session}
              />
            ))}
          </section>
        )}

        {availableSources.length > 0 && (
          <section aria-labelledby="history-sources-title" className="sidebar__section">
            <h2 id="history-sources-title" className="sidebar__section-title">Geçmiş kaynakları</h2>
            {availableSources.map((source) => (
              <NavItem
                icon="changes"
                key={source}
                label={`${source[0].toLocaleUpperCase("tr")}${source.slice(1)} geçmişi`}
                onClick={() => onNavigate(`resume:${source}`)}
              />
            ))}
          </section>
        )}
      </div>

      <div className="sidebar__bottom">
        <NavItem icon="skills" label="Beceriler ve Ajanlar" onClick={() => onNavigate("skills")} />
        <NavItem icon="lessons" label="Dersler" onClick={() => onNavigate("lessons")} />
        <NavItem icon="panel" label="Kontrol Paneli" onClick={() => onNavigate("control-panel")} />
        <NavItem icon="settings" label="Ayarlar" onClick={() => onNavigate("settings")} />
      </div>
    </nav>
  );
}

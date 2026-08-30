import { useEffect, useMemo, useState } from "react";
import { Icon, type IconName } from "../ui/Icon";
import { Logo } from "../brand/Logo";
import { SourceIcon } from "../brand/SourceIcon";
import "./Sidebar.css";

export interface OturumSatiri {
  project?: string;
  session_id: string;
  source: string;
  title: string;
}

export interface ProjeSatiri {
  name: string;
  pinned: boolean;
  root: string;
  updated_at: number;
}

type HistorySource = "fusion" | "claude" | "codex" | "hermes";

interface SidebarProps {
  availableSources?: HistorySource[];
  collapsed?: boolean;
  etkin: string | null;
  onNavigate?: (destination: string) => void;
  onSec: (id: string) => void;
  onSil?: (id: string) => void;
  onYeni: () => void;
  oturumlar: OturumSatiri[];
  projeler?: ProjeSatiri[];
}

interface NavItemProps {
  icon: IconName;
  label: string;
  onClick?: () => void;
}

/** Kenar çubuğunun ikon şeridine indiği eşik. */
const DAR_EKRAN = "(max-width: 1199px)";

function useDarEkran(): boolean {
  const [dar, setDar] = useState(() => window.matchMedia?.(DAR_EKRAN).matches ?? false);
  useEffect(() => {
    if (!window.matchMedia) return;
    const media = window.matchMedia(DAR_EKRAN);
    const onChange = (event: MediaQueryListEvent) => setDar(event.matches);
    setDar(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);
  return dar;
}

function NavItem({ icon, label, onClick }: NavItemProps) {
  return (
    <button aria-label={label} className="sidebar__nav-item" onClick={onClick} type="button">
      <Icon name={icon} size={18} />
      <span className="sidebar__label">{label}</span>
    </button>
  );
}

function SessionButton({ session, active, onSelect, onDelete }: {
  session: OturumSatiri;
  active: boolean;
  onSelect: () => void;
  onDelete?: () => void;
}) {
  // Silme İKİ adımdır: sohbet geri getirilemez, tek tıkla gitmemeli.
  const [confirming, setConfirming] = useState(false);
  return (
    <div className="sidebar__session-row">
      <button
        aria-label={session.title}
        className="sidebar__session"
        data-etkin={active}
        onClick={onSelect}
        type="button"
      >
        <SourceIcon size={16} source={session.source} />
        <span className="sidebar__session-title">{session.title}</span>
        <span className="sidebar__session-source">
          {session.source}{session.project ? ` · ${session.project}` : ""}
        </span>
      </button>
      {onDelete && (
        confirming ? (
          <span className="sidebar__session-confirm">
            <button aria-label={`${session.title} sohbetini kalıcı olarak sil`} onClick={onDelete} type="button">
              Sil
            </button>
            <button aria-label="Silmekten vazgeç" onClick={() => setConfirming(false)} type="button">
              Vazgeç
            </button>
          </span>
        ) : (
          <button
            aria-label={`${session.title} sohbetini sil`}
            className="sidebar__session-delete"
            onClick={() => setConfirming(true)}
            type="button"
          >
            ×
          </button>
        )
      )}
    </div>
  );
}

export function Sidebar({
  availableSources = [],
  collapsed = false,
  etkin,
  onNavigate = () => undefined,
  onSec,
  onSil,
  onYeni,
  oturumlar,
  projeler = [],
}: SidebarProps) {
  // Dar pencerede kenar çubuğu kendiliğinden ikon şeridine iner. Bu KARAR
  // burada verilir çünkü dar kip kuralları `data-collapsed` seçicisine bağlıdır;
  // eskiden bir CSS değişkeni hilesiyle yapılıyordu ve o hile, geniş kipte
  // temel `display`/`padding` değerlerini de siliyordu (ölçüldü).
  const darEkran = useDarEkran();
  const [query, setQuery] = useState("");
  const [historyExpanded, setHistoryExpanded] = useState(() =>
    typeof localStorage === "undefined" || localStorage.getItem("fusion.sidebar.history-open.v1") !== "false",
  );
  const filteredSessions = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("tr");
    if (!normalized) return oturumlar;
    return oturumlar.filter((session) =>
      `${session.title} ${session.source} ${session.project ?? ""}`
        .toLocaleLowerCase("tr")
        .includes(normalized),
    );
  }, [oturumlar, query]);
  const filteredProjects = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase("tr");
    const matches = normalized
      ? projeler.filter((project) =>
          `${project.name} ${project.root}`.toLocaleLowerCase("tr").includes(normalized),
        )
      : projeler;
    return [...matches].sort((left, right) => {
      if (left.pinned !== right.pinned) return left.pinned ? -1 : 1;
      return right.updated_at - left.updated_at;
    });
  }, [projeler, query]);
  /** Sohbetleri projeye göre grupla; projesizler "Sohbetler" altında toplanır.
   *  Kullanıcı ChatGPT'deki gibi bir proje altında sohbetlerini görmek istedi. */
  const sessionGroups = useMemo(() => {
    const gruplar = new Map<string, OturumSatiri[]>();
    for (const session of filteredSessions) {
      const ad = session.project?.trim() || "Sohbetler";
      const mevcut = gruplar.get(ad);
      if (mevcut) mevcut.push(session);
      else gruplar.set(ad, [session]);
    }
    // Projesiz sohbetler en sonda: adlandırılmış projeler önce görünür.
    return [...gruplar.entries()].sort(([sol], [sag]) =>
      sol === "Sohbetler" ? 1 : sag === "Sohbetler" ? -1 : sol.localeCompare(sag, "tr"),
    );
  }, [filteredSessions]);

  const pinnedProjects = filteredProjects.filter((project) => project.pinned);
  const recentProjects = filteredProjects.filter((project) => !project.pinned);
  const hasHistory = sessionGroups.length > 0 || availableSources.length > 0;
  const toggleHistory = () => setHistoryExpanded((current) => {
    const next = !current;
    localStorage.setItem("fusion.sidebar.history-open.v1", String(next));
    return next;
  });

  const projectSection = (title: string, projects: ProjeSatiri[]) => projects.length > 0 && (
    <section aria-label={title} className="sidebar__section">
      <h2 className="sidebar__section-title">{title}</h2>
      {projects.map((project) => (
        <button
          aria-label={`${project.name} projesini aç`}
          className="sidebar__project"
          key={project.root}
          onClick={() => onNavigate(`project:${project.root}`)}
          type="button"
        >
          <Icon name="files" size={17} />
          <span className="sidebar__label">{project.name}</span>
        </button>
      ))}
    </section>
  );

  return (
    <nav aria-label="Fusion" className="sidebar" data-collapsed={collapsed || darEkran}>
      <div className="sidebar__top">
        <div aria-label="Fusion" className="sidebar__brand">
          <Logo size={24} />
          <span className="sidebar__label fusion-wordmark">Fusion</span>
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
        {projectSection("Sabit projeler", pinnedProjects)}
        {projectSection("Yakın projeler", recentProjects)}
        {hasHistory && (
          <section aria-label="Geçmiş" className="sidebar__history">
            <button
              aria-expanded={historyExpanded}
              aria-label={historyExpanded ? "Geçmişi daralt" : "Geçmişi genişlet"}
              className="sidebar__history-toggle"
              onClick={toggleHistory}
              type="button"
            >
              <span className="sidebar__label">Geçmiş</span>
              <Icon name="chevron" size={15} />
            </button>
            {historyExpanded && (
              <div className="sidebar__history-body">
                {sessionGroups.map(([projectName, groupSessions]) => (
                  <section aria-label={projectName} className="sidebar__section" key={projectName}>
                    <h2 className="sidebar__section-title">{projectName}</h2>
                    {groupSessions.map((session) => (
                      <SessionButton
                        active={session.session_id === etkin}
                        key={session.session_id}
                        onDelete={onSil ? () => onSil(session.session_id) : undefined}
                        onSelect={() => onSec(session.session_id)}
                        session={session}
                      />
                    ))}
                  </section>
                ))}
                {availableSources.length > 0 && (
                  <section aria-labelledby="history-sources-title" className="sidebar__section">
                    <h2 id="history-sources-title" className="sidebar__section-title">Devam et</h2>
                    {availableSources.map((source) => {
                      const label = `${source[0].toLocaleUpperCase("tr")}${source.slice(1)} geçmişi`;
                      return (
                        <button
                          aria-label={label}
                          className="sidebar__nav-item"
                          key={source}
                          onClick={() => onNavigate(`resume:${source}`)}
                          type="button"
                        >
                          <SourceIcon source={source} />
                          <span className="sidebar__label">{label}</span>
                        </button>
                      );
                    })}
                  </section>
                )}
              </div>
            )}
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

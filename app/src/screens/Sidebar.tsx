import { useEffect, useMemo, useRef, useState } from "react";
import { Icon, type IconName } from "../ui/Icon";
import { Logo } from "../brand/Logo";
import { SourceIcon } from "../brand/SourceIcon";
import "./Sidebar.css";

export interface OturumSatiri {
  project?: string;
  projectRoot?: string;
  updated_at?: number;
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
  onSil?: (id: string) => void | Promise<void>;
  onYeni: () => void;
  oturumlar: OturumSatiri[];
  projeler?: ProjeSatiri[];
  /** Yalnız arka ucun bağlı diye bildirdiği gerçek web oturumundan gelir. */
  webProfile?: { account: string; providerName: string } | null;
}

interface NavItemProps {
  /** Ders ışığının yakalayacağı nişan; yalnız derslerde adı geçen öğelerde. */
  ders?: string;
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

function NavItem({ ders, icon, label, onClick }: NavItemProps) {
  return (
    <button
      aria-label={label}
      className="sidebar__nav-item"
      data-ders={ders}
      onClick={onClick}
      type="button"
    >
      <Icon name={icon} size={18} />
      <span className="sidebar__label">{label}</span>
    </button>
  );
}

function SessionButton({ session, active, onSelect, onDelete, pinned, onPin }: {
  pinned: boolean;
  onPin: () => void;
  session: OturumSatiri;
  active: boolean;
  onSelect: () => void;
  onDelete?: () => void | Promise<void>;
}) {
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  return (
    <div className="sidebar__session-row">
      <button
        aria-label={session.title}
        className="sidebar__session"
        data-etkin={active}
        onClick={onSelect}
        type="button"
      >
        {/* Marka rozeti yalnız İÇE AKTARILMIŞ konuşmalarda anlamlıdır: hangi
            araçtan geldiğini söyler. Fusion'ın kendi sohbetlerinde her satıra
            aynı logoyu basmak bilgi taşımaz, listeyi gürültüye çevirir.
            Yerine nötr bir işaret durur: dar kipte başlık gizlendiği için
            satırın tamamen boş kalmaması gerekir. */}
        {session.source === "fusion"
          ? <span aria-hidden="true" className="source-icon sidebar__session-dot" />
          : <SourceIcon size={16} source={session.source} />}
        <span className="sidebar__session-title">{session.title}</span>
        <span className="sidebar__session-source">
          {session.source === "fusion" ? "" : session.source}
        </span>
      </button>
      <button aria-label={`${session.title} sohbetini ${pinned ? "sabitlemekten çıkar" : "sabitle"}`} aria-pressed={pinned} className="sidebar__session-pin" onClick={onPin} type="button"><svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill={pinned ? "currentColor" : "none"} stroke="currentColor" strokeWidth="1.6"><path d="m16 3 5 5-4 2-2 5-3 1-4-4 1-3 5-2zM9 15l-6 6" /></svg></button>
      {onDelete && <button
        aria-label={`${session.title} sohbetini sil`}
        className="sidebar__session-delete"
        disabled={deleting}
        onClick={() => {
          setDeleting(true);
          setDeleteError(null);
          void Promise.resolve().then(onDelete)
            .catch(() => setDeleteError("Sohbet silinemedi. Yeniden dene."))
            .finally(() => setDeleting(false));
        }}
        type="button"
      ><svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7" /></svg></button>}
      {deleteError && <span role="alert">{deleteError}</span>}
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
  webProfile = null,
}: SidebarProps) {
  // Dar pencerede kenar çubuğu kendiliğinden ikon şeridine iner. Bu KARAR
  // burada verilir çünkü dar kip kuralları `data-collapsed` seçicisine bağlıdır;
  // eskiden bir CSS değişkeni hilesiyle yapılıyordu ve o hile, geniş kipte
  // temel `display`/`padding` değerlerini de siliyordu (ölçüldü).
  const darEkran = useDarEkran();
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [pinnedSessions, setPinnedSessions] = useState<string[]>(() => {
    try {
      const saved: unknown = JSON.parse(localStorage.getItem("fusion.sidebar.pinned-sessions.v1") ?? "[]");
      return Array.isArray(saved) ? saved.filter((item): item is string => typeof item === "string") : [];
    } catch { return []; }
  });
  const [pinError, setPinError] = useState<string | null>(null);
  useEffect(() => {
    try {
      localStorage.setItem("fusion.sidebar.pinned-sessions.v1", JSON.stringify(pinnedSessions));
      setPinError(null);
    } catch {
      setPinError("Sabitleme tercihi kaydedilemedi; bu pencere açıkken korunacak.");
    }
  }, [pinnedSessions]);
  const pinKey = (session: OturumSatiri) => `${session.projectRoot ?? session.project ?? ""}:${session.source}:${session.session_id}`;
  const togglePin = (session: OturumSatiri) => setPinnedSessions((current) => {
    const key = pinKey(session);
    const next = current.includes(key) ? current.filter((item) => item !== key) : [...current, key];
    return next;
  });
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
  const sessionGroups = useMemo(() => {
    const groups = new Map<string, { name: string; root?: string; sessions: OturumSatiri[] }>();
    for (const project of filteredProjects) groups.set(project.root, { name: project.name, root: project.root, sessions: [] });
    for (const session of filteredSessions) {
      const project = projeler.find((item) => session.projectRoot ? item.root === session.projectRoot : item.name === session.project);
      const key = session.projectRoot ?? project?.root ?? session.project ?? "Sohbetler";
      if (!groups.has(key)) groups.set(key, { name: session.project || "Sohbetler", root: session.projectRoot ?? project?.root, sessions: [] });
      groups.get(key)!.sessions.push(session);
    }
    for (const group of groups.values()) group.sessions.sort((a, b) => {
      const pinOrder = Number(pinnedSessions.includes(pinKey(b))) - Number(pinnedSessions.includes(pinKey(a)));
      return pinOrder || (b.updated_at ?? 0) - (a.updated_at ?? 0);
    });
    return [...groups.entries()];
  }, [filteredProjects, filteredSessions, pinnedSessions, projeler]);
  const hasHistory = sessionGroups.length > 0 || availableSources.length > 0;
  const toggleHistory = () => setHistoryExpanded((current) => {
    const next = !current;
    localStorage.setItem("fusion.sidebar.history-open.v1", String(next));
    return next;
  });

  useEffect(() => {
    if (!profileOpen) return;
    const closeOnOutside = (event: MouseEvent) => {
      if (!profileRef.current?.contains(event.target as Node)) setProfileOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setProfileOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [profileOpen]);

  const navigateFromProfile = (destination: string) => {
    setProfileOpen(false);
    onNavigate(destination);
  };
  const profileName = webProfile?.providerName ?? "Yerel profil";
  const profileMenuLabel = webProfile ? `${profileName} profil menüsü` : "Yerel profil menüsü";
  const profileDetail = webProfile ? `${webProfile.account} hesabı bağlı` : "Bağlantı yok";
  const profileInitials = webProfile
    ? webProfile.providerName.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toLocaleUpperCase("tr")
    : "FP";

  return (
    <nav aria-label="Fusion" className="sidebar" data-collapsed={collapsed || darEkran}>
      <div className="sidebar__top">
        <div aria-label="Fusion" className="sidebar__brand">
          <Logo size={24} />
          <span className="sidebar__label fusion-wordmark">Fusion</span>
          <button aria-label="Konuşma ve proje aramasını aç" aria-expanded={searchOpen} className="sidebar__search-trigger" onClick={() => setSearchOpen((open) => !open)} type="button"><Icon name="search" size={19} /></button>
        </div>
        <NavItem ders="yeni-gorev" icon="new" label="Yeni sohbet" onClick={onYeni} />
        <NavItem icon="image" label="Görsel oluştur" onClick={() => onNavigate("image-create")} />
        <NavItem icon="video" label="Video oluştur" onClick={() => onNavigate("video-create")} />
        {searchOpen && <label className="sidebar__search" data-ders="arama">
          <Icon name="search" size={17} />
          <span className="sidebar__sr-only">Konuşma ve proje ara</span>
          <input
            autoFocus
            aria-label="Konuşma ve proje ara"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ara"
            type="search"
            value={query}
          />
        </label>}
      </div>

      <div className="sidebar__scroll">
        {pinError && <p role="alert" className="sidebar__storage-error">{pinError}</p>}
        {hasHistory && (
          <section aria-label="Geçmiş" className="sidebar__history">
            <button
              aria-expanded={historyExpanded}
              aria-label={historyExpanded ? "Geçmişi daralt" : "Geçmişi genişlet"}
              className="sidebar__history-toggle"
              data-ders="gecmis"
              onClick={toggleHistory}
              type="button"
            >
              <span className="sidebar__label">Geçmiş</span>
              <Icon name="chevron" size={15} />
            </button>
            {historyExpanded && (
              <div className="sidebar__history-body">
                {sessionGroups.map(([groupKey, group]) => (
                  <section aria-label={group.name} className="sidebar__section" key={groupKey}>
                    <h2 className="sidebar__section-title">{group.root ? <button aria-label={`${group.name} projesini aç`} className="sidebar__project" onClick={() => onNavigate(`project:${group.root}`)} type="button"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3 7V5a2 2 0 0 1 2-2h5l3 3h6a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7h18" /></svg><span className="sidebar__label">{group.name}</span></button> : group.name}</h2>
                    {(expandedGroups.has(groupKey) || query.trim() ? group.sessions : group.sessions.slice(0, 5)).map((session) => (
                      <SessionButton
                        pinned={pinnedSessions.includes(pinKey(session))}
                        onPin={() => togglePin(session)}
                        active={session.session_id === etkin}
                        key={session.session_id}
                        onDelete={onSil ? async () => { await onSil(session.session_id); setPinnedSessions((current) => current.filter((key) => key !== pinKey(session))); } : undefined}
                        onSelect={() => onSec(session.session_id)}
                        session={session}
                      />
                    ))}
                    {group.sessions.length > 5 && !query.trim() && <button aria-label={`${group.name}: ${expandedGroups.has(groupKey) ? "Daha az göster" : "Daha fazla göster"}`} className="sidebar__more" onClick={() => setExpandedGroups((current) => { const next = new Set(current); if (next.has(groupKey)) next.delete(groupKey); else next.add(groupKey); return next; })} type="button">{expandedGroups.has(groupKey) ? "Daha az göster" : "Daha fazla göster"}</button>}
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
        <div className="sidebar__profile-wrap" ref={profileRef}>
          {profileOpen && (
            <div aria-label="Profil menüsü" className="sidebar__profile-menu" role="menu">
              <button className="sidebar__profile-heading" onClick={() => navigateFromProfile("settings")} role="menuitem" type="button">
                <span className="sidebar__avatar">{profileInitials}</span>
                <span className="sidebar__profile-copy"><strong>{profileName}</strong><small>{profileDetail}</small></span>
                <Icon className="sidebar__profile-chevron" name="chevron" size={20} />
              </button>
              <div className="sidebar__profile-separator" />
              <button data-ders="kontrol-paneli" onClick={() => navigateFromProfile("control-panel")} role="menuitem" type="button"><Icon name="panel" /><span>Kontrol Merkezi</span></button>
              <button onClick={() => navigateFromProfile("skills")} role="menuitem" type="button"><Icon name="skills" /><span>Beceriler ve Ajanlar</span></button>
              <button onClick={() => navigateFromProfile("connectors")} role="menuitem" type="button"><Icon name="terminal" /><span>MCP bağlantıları</span></button>
              <button data-ders="dersler" onClick={() => navigateFromProfile("lessons")} role="menuitem" type="button"><Icon name="lessons" /><span>Dersler</span></button>
              <button data-ders="ayarlar" onClick={() => navigateFromProfile("settings")} role="menuitem" type="button"><Icon name="settings" /><span>Ayarlar</span></button>
              <div className="sidebar__profile-separator" />
              <button onClick={() => navigateFromProfile("help")} role="menuitem" type="button"><Icon name="help" /><span>Yardım</span><Icon className="sidebar__profile-chevron" name="chevron" size={18} /></button>
            </div>
          )}
          <button
            aria-expanded={profileOpen}
            aria-haspopup="menu"
            aria-label={profileMenuLabel}
            className="sidebar__profile-trigger"
            onClick={() => setProfileOpen((open) => !open)}
            type="button"
          >
            <span className="sidebar__avatar">{profileInitials}</span>
            <span className="sidebar__profile-copy sidebar__label"><strong>{profileName}</strong><small>{profileDetail}</small></span>
            <span aria-hidden="true" className="sidebar__profile-status" data-connected={Boolean(webProfile)} />
          </button>
        </div>
      </div>
    </nav>
  );
}

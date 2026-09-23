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

interface ProjectPreference { hidden?: boolean; name?: string; pinned?: boolean }

function readProjectPreferences(): Record<string, ProjectPreference> {
  try {
    const value: unknown = JSON.parse(localStorage.getItem("fusion.sidebar.projects.v1") ?? "{}");
    return value && typeof value === "object" && !Array.isArray(value)
      ? value as Record<string, ProjectPreference> : {};
  } catch { return {}; }
}

type HistorySource = "fusion" | "claude" | "codex" | "hermes";

interface SidebarProps {
  availableSources?: HistorySource[];
  collapsed?: boolean;
  etkin: string | null;
  onNavigate?: (destination: string) => void;
  onSec: (id: string) => void;
  onSil?: (id: string) => void | Promise<void>;
  onMove?: (id: string, targetRoot: string) => Promise<void>;
  onYeni: () => void;
  oturumlar: OturumSatiri[];
  projeler?: ProjeSatiri[];
  /** Sol alttaki satır: giriş yapmış YEREL HESAP.
   *
   * Eskiden burada web sağlayıcısının adı ("Gemini Web") yazıyordu ve kullanıcı
   * adı gibi görünüyordu; hesap kavramı henüz yoktu. Artık gerçek hesap durur.
   */
  hesap?: { kullanici_adi: string; eposta: string; avatar: string } | null;
  onCikis?: () => void;
  /** Yeni sürüm varsa numarası; yoksa şerit hiç çizilmez. */
  guncellemeSurumu?: string | null;
  onGuncellemeAc?: () => void;
}

interface NavItemProps {
  icon: IconName;
  label: string;
  onClick?: () => void;
}

function NavItem({ icon, label, onClick }: NavItemProps) {
  return (
    <button
      aria-label={label}
      className="sidebar__nav-item"
      onClick={onClick}
      type="button"
    >
      <Icon name={icon} size={18} />
      <span className="sidebar__label">{label}</span>
    </button>
  );
}

function SessionButton({ session, active, onSelect, onDelete, onMove, moveTargets, pinned, onPin }: {
  pinned: boolean;
  onPin: () => void;
  session: OturumSatiri;
  active: boolean;
  onSelect: () => void;
  onDelete?: () => void | Promise<void>;
  onMove?: (root: string) => Promise<void>;
  moveTargets: ProjeSatiri[];
}) {
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [moveOpen, setMoveOpen] = useState(false);
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
      {onMove && moveTargets.length > 0 && <div className="sidebar__move-wrap">
        <button aria-expanded={moveOpen} aria-label={`${session.title} sohbetini projeye taşı`} className="sidebar__session-move" onClick={() => setMoveOpen((open) => !open)} type="button">···</button>
        {moveOpen && <div aria-label="Hedef proje" className="sidebar__move-menu" role="menu">
          <strong>Projeye taşı</strong>
          {moveTargets.map((project) => <button key={project.root} onClick={() => {
            setMoveOpen(false);
            void onMove(project.root).catch((error: unknown) => setDeleteError(String(error)));
          }} role="menuitem" type="button">{project.name}</button>)}
        </div>}
      </div>}
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
  onMove,
  onYeni,
  oturumlar,
  projeler = [],
  hesap = null,
  onCikis,
  guncellemeSurumu = null,
  onGuncellemeAc,
}: SidebarProps) {
  const [profileOpen, setProfileOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [projectPreferences, setProjectPreferences] = useState(readProjectPreferences);
  const [projectMenu, setProjectMenu] = useState<string | null>(null);
  const [projectDialog, setProjectDialog] = useState<{ root: string; kind: "rename" | "remove" } | null>(null);
  const [projectDraft, setProjectDraft] = useState("");
  useEffect(() => {
    try { localStorage.setItem("fusion.sidebar.projects.v1", JSON.stringify(projectPreferences)); }
    catch { /* Geçici görünüm bu oturumda kullanılabilir kalır. */ }
  }, [projectPreferences]);
  const updateProject = (root: string, patch: ProjectPreference) => {
    setProjectPreferences((current) => ({
      ...current,
      [root]: { ...current[root], ...patch },
    }));
  };
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
    const available = projeler
      .filter((project) => !projectPreferences[project.root]?.hidden && project.name !== "Desktop")
      .map((project) => ({
        ...project,
        name: projectPreferences[project.root]?.name || project.name,
        pinned: projectPreferences[project.root]?.pinned ?? project.pinned,
      }));
    const matches = normalized
      ? available.filter((project) =>
          `${project.name} ${project.root}`.toLocaleLowerCase("tr").includes(normalized),
        )
      : available;
    return [...matches].sort((left, right) => {
      if (left.pinned !== right.pinned) return left.pinned ? -1 : 1;
      return right.updated_at - left.updated_at;
    });
  }, [projectPreferences, projeler, query]);
  const sessionGroups = useMemo(() => {
    const groups = new Map<string, { name: string; root?: string; sessions: OturumSatiri[] }>();
    for (const project of filteredProjects) groups.set(project.root, { name: project.name, root: project.root, sessions: [] });
    for (const session of filteredSessions) {
      const project = filteredProjects.find((item) => session.projectRoot ? item.root === session.projectRoot : item.name === session.project);
      const looseName = !session.projectRoot && session.project !== "Desktop"
        ? session.project : undefined;
      const key = project?.root ?? looseName ?? "Sohbetler";
      if (!groups.has(key)) groups.set(key, { name: project?.name ?? looseName ?? "Sohbetler", root: project?.root, sessions: [] });
      groups.get(key)!.sessions.push(session);
    }
    for (const group of groups.values()) group.sessions.sort((a, b) => {
      const pinOrder = Number(pinnedSessions.includes(pinKey(b))) - Number(pinnedSessions.includes(pinKey(a)));
      return pinOrder || (b.updated_at ?? 0) - (a.updated_at ?? 0);
    });
    return [...groups.entries()];
  }, [filteredProjects, filteredSessions, pinnedSessions]);
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
  const profileName = hesap?.kullanici_adi ?? "Hesap yok";
  const profileMenuLabel = hesap ? `${profileName} hesap menüsü` : "Hesap menüsü";
  const profileDetail = hesap?.eposta ?? "Giriş yapılmadı";
  const profileInitials =
    hesap?.avatar ||
    (hesap
      ? hesap.kullanici_adi.split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toLocaleUpperCase("tr")
      : "?");

  return (
    <nav aria-label="Fusion" className="sidebar" data-collapsed={collapsed}>
      <div className="sidebar__top">
        <div aria-label="Fusion" className="sidebar__brand">
          <Logo size={24} />
          <span className="sidebar__label fusion-wordmark">Fusion</span>
          <button aria-label="Konuşma ve proje aramasını aç" aria-expanded={searchOpen} className="sidebar__search-trigger" onClick={() => setSearchOpen((open) => !open)} type="button"><Icon name="search" size={19} /></button>
        </div>
        <NavItem icon="new" label="Yeni sohbet" onClick={onYeni} />
        <NavItem icon="image" label="Görsel oluştur" onClick={() => onNavigate("image-create")} />
        <NavItem icon="video" label="Video oluştur" onClick={() => onNavigate("video-create")} />
        {searchOpen && <label className="sidebar__search">
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
              onClick={toggleHistory}
              type="button"
            >
              <span className="sidebar__label">Geçmiş</span>
              <Icon name="chevron" size={15} />
            </button>
            {historyExpanded && (
              <div className="sidebar__history-body">
                <div className="sidebar__projects-heading">
                  <span>Projeler</span>
                  <button aria-label="Yeni proje" onClick={() => onNavigate("new-project")} type="button">+</button>
                </div>
                {projeler.filter((project) => projectPreferences[project.root]?.hidden).map((project) => (
                  <button className="sidebar__restore-project" key={project.root} onClick={() => updateProject(project.root, { hidden: false })} type="button">{project.name} projesini geri ekle</button>
                ))}
                {sessionGroups.map(([groupKey, group]) => (
                  <section aria-label={group.name} className="sidebar__section" key={groupKey}>
                    <h2 className="sidebar__section-title">{group.root ? <span className="sidebar__project-row"><button aria-label={`${group.name} projesini aç`} className="sidebar__project" onClick={() => onNavigate(`project:${group.root}`)} type="button"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M3 7V5a2 2 0 0 1 2-2h5l3 3h6a2 2 0 0 1 2 2v11a2 2 0 0 1-2-2V7h18" /></svg><span className="sidebar__label">{group.name}</span></button><button aria-expanded={projectMenu === group.root} aria-label={`${group.name} için proje seçeneklerini aç`} className="sidebar__project-options" onClick={() => setProjectMenu(projectMenu === group.root ? null : group.root!)} type="button">···</button></span> : group.name}</h2>
                    {group.root && projectMenu === group.root && <div aria-label={`${group.name} proje seçenekleri`} className="sidebar__project-menu" role="menu">
                      <button onClick={() => { setProjectDraft(group.name); setProjectDialog({ root: group.root!, kind: "rename" }); setProjectMenu(null); }} role="menuitem" type="button">Projeyi yeniden adlandır</button>
                      <button onClick={() => { updateProject(group.root!, { pinned: !projectPreferences[group.root!]?.pinned }); setProjectMenu(null); }} role="menuitem" type="button">{projectPreferences[group.root]?.pinned ? "Sabitlemeyi kaldır" : "Projeyi sabitle"}</button>
                      <button onClick={() => { setProjectDialog({ root: group.root!, kind: "remove" }); setProjectMenu(null); }} role="menuitem" type="button">Projeyi sil</button>
                    </div>}
                    {(expandedGroups.has(groupKey) || query.trim() ? group.sessions : group.sessions.slice(0, 5)).map((session) => (
                      <SessionButton
                        moveTargets={filteredProjects.filter((project) => project.root !== group.root)}
                        onMove={onMove ? (root) => onMove(session.session_id, root) : undefined}
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

      {projectDialog && <div className="sidebar__project-backdrop" role="presentation">
        <div aria-label={projectDialog.kind === "rename" ? "Projeyi yeniden adlandır" : "Projeyi sil"} aria-modal="true" className="sidebar__project-dialog" role="dialog">
          <h2>{projectDialog.kind === "rename" ? "Projeyi yeniden adlandır" : "Projeyi sil"}</h2>
          {projectDialog.kind === "rename" ? <input aria-label="Proje adı" autoFocus maxLength={80} onChange={(event) => setProjectDraft(event.target.value)} value={projectDraft} /> : <p>Proje Fusion listesinden kaldırılır. Bilgisayarındaki klasörler ve sohbet kayıtları korunur.</p>}
          <div><button onClick={() => setProjectDialog(null)} type="button">Vazgeç</button><button disabled={projectDialog.kind === "rename" && !projectDraft.trim()} onClick={() => { updateProject(projectDialog.root, projectDialog.kind === "rename" ? { name: projectDraft.trim() } : { hidden: true }); setProjectDialog(null); }} type="button">{projectDialog.kind === "rename" ? "Kaydet" : "Listeden kaldır"}</button></div>
        </div>
      </div>}

      <div className="sidebar__bottom">
        {/* Güncelleme şeridi profilin HEMEN ÜSTÜNDE durur: kullanıcı yeni sürümü
            aramak zorunda kalmasın. Sürüm yoksa hiç çizilmez — boş bir satır
            "bir şey var mı?" sorusunu her açılışta yeniden sordururdu. */}
        {guncellemeSurumu && onGuncellemeAc && (
          <button className="sidebar__update" onClick={onGuncellemeAc} type="button">
            <span className="sidebar__update-dot" aria-hidden="true" />
            <span className="sidebar__label">{guncellemeSurumu} sürümü hazır</span>
          </button>
        )}
        <div className="sidebar__profile-wrap" ref={profileRef}>
          {profileOpen && (
            <div aria-label="Profil menüsü" className="sidebar__profile-menu" role="menu">
              <button className="sidebar__profile-heading" onClick={() => navigateFromProfile("account")} role="menuitem" type="button">
                <span className="sidebar__avatar">{profileInitials}</span>
                <span className="sidebar__profile-copy"><strong>{profileName}</strong><small>{profileDetail}</small></span>
                <Icon className="sidebar__profile-chevron" name="chevron" size={20} />
              </button>
              <div className="sidebar__profile-separator" />
              <button onClick={() => navigateFromProfile("account")} role="menuitem" type="button"><Icon name="settings" /><span>Hesabım</span></button>
              <button onClick={() => navigateFromProfile("settings")} role="menuitem" type="button"><Icon name="settings" /><span>Ayarlar</span></button>
              <button onClick={() => navigateFromProfile("control-panel")} role="menuitem" type="button"><Icon name="panel" /><span>Kontrol Paneli</span></button>
              <button onClick={() => navigateFromProfile("skills")} role="menuitem" type="button"><Icon name="skills" /><span>Beceriler ve Ajanlar</span></button>
              <button onClick={() => navigateFromProfile("connectors")} role="menuitem" type="button"><Icon name="terminal" /><span>MCP bağlantıları</span></button>
              <button onClick={() => navigateFromProfile("help")} role="menuitem" type="button"><Icon name="help" /><span>Yardım</span></button>
              <button onClick={() => navigateFromProfile("language")} role="menuitem" type="button"><Icon name="lessons" /><span>Dil</span></button>
              <div className="sidebar__profile-separator" />
              <button onClick={() => { setProfileOpen(false); onCikis?.(); }} role="menuitem" type="button"><Icon name="help" /><span>Çıkış yap</span></button>
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
            <span aria-hidden="true" className="sidebar__profile-status" data-connected={Boolean(hesap)} />
          </button>
        </div>
      </div>
    </nav>
  );
}

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Icon, type IconName } from "../ui/Icon";
import { Logo } from "../brand/Logo";
import { SourceIcon } from "../brand/SourceIcon";
import "./Sidebar.css";

export interface OturumSatiri {
  project?: string;
  projectRoot?: string;
  /** Kalıcı proje kaydına bağlıysa onun kimliği; yoksa sohbet "Sohbetler" altındadır. */
  projectId?: string;
  updated_at?: number;
  session_id: string;
  source: string;
  title: string;
}

export interface ProjeSatiri {
  /** Yalnız kalıcı proje kayıtlarında vardır; klasörden türeyen projelerde yoktur. */
  id?: string;
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
  /** Ana menü rayındaki hesap yuvası; null iken yuva henüz bağlanmadı. */
  profileHost?: HTMLElement | null;
  availableSources?: HistorySource[];
  collapsed?: boolean;
  etkin: string | null;
  onNavigate?: (destination: string) => void;
  onSec: (id: string) => void;
  onSil?: (id: string) => void | Promise<void>;
  onMove?: (id: string, targetRoot: string) => Promise<void>;
  /** Kalıcı proje kayıtları: oluştur / yeniden adlandır / sil / sohbeti ata. */
  onProjectCreate?: (input: { name: string; root?: string }) => void | Promise<void>;
  onProjectRename?: (id: string, name: string) => void | Promise<void>;
  onProjectDelete?: (id: string) => void | Promise<void>;
  onAssign?: (sessionId: string, projectId: string | null) => void | Promise<void>;
  /** Yeni proje için isteğe bağlı klasör seçici; iptalde null. */
  onPickFolder?: () => Promise<string | null>;
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

interface MoveTarget { key: string; name: string; run: () => void | Promise<void> }

function SessionButton({ session, active, onSelect, onDelete, onRemoveFromProject, moveTargets, pinned, onPin }: {
  pinned: boolean;
  onPin: () => void;
  session: OturumSatiri;
  active: boolean;
  onSelect: () => void;
  onDelete?: () => void | Promise<void>;
  onRemoveFromProject?: () => void | Promise<void>;
  moveTargets: MoveTarget[];
}) {
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const menuPopupRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!menuOpen || !menuButtonRef.current || !menuPopupRef.current) return;
    const button = menuButtonRef.current.getBoundingClientRect();
    const menu = menuPopupRef.current;
    const below = button.bottom + 4;
    const above = button.top - menu.offsetHeight - 4;
    menu.style.top = `${Math.max(8, Math.min(
      below + menu.offsetHeight <= window.innerHeight - 8 ? below : above,
      window.innerHeight - menu.offsetHeight - 8,
    ))}px`;
    menu.style.left = `${Math.max(8, Math.min(
      button.right - menu.offsetWidth,
      window.innerWidth - menu.offsetWidth - 8,
    ))}px`;
  }, [menuOpen]);
  useEffect(() => {
    if (!menuOpen) return;
    const close = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)
        && !menuPopupRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("pointerdown", close);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", close);
      document.removeEventListener("keydown", escape);
    };
  }, [menuOpen]);
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
      <div className="sidebar__move-wrap" ref={menuRef}>
        <button aria-expanded={menuOpen} aria-haspopup="menu" aria-label={`${session.title} sohbet seçenekleri`} className="sidebar__session-move" onClick={() => setMenuOpen((open) => !open)} ref={menuButtonRef} type="button">···</button>
        {menuOpen && createPortal(<div aria-label={`${session.title} sohbet seçenekleri`} className="sidebar__move-menu" ref={menuPopupRef} role="menu">
          <button aria-checked={pinned} onClick={() => { onPin(); setMenuOpen(false); }} role="menuitemcheckbox" type="button">{pinned ? "Sabitlemeyi kaldır" : "Sabitle"}</button>
          {moveTargets.length > 0 && <>
            <strong>Projeye taşı</strong>
            {moveTargets.map((target) => <button key={target.key} onClick={() => {
              setMenuOpen(false);
              void Promise.resolve().then(target.run).catch((error: unknown) => setDeleteError(String(error)));
            }} role="menuitem" type="button">{target.name}</button>)}
          </>}
          {onRemoveFromProject && <button onClick={() => {
            setMenuOpen(false);
            void Promise.resolve().then(onRemoveFromProject).catch((error: unknown) => setDeleteError(String(error)));
          }} role="menuitem" type="button">Projeden çıkar</button>}
          {onDelete && <button className="sidebar__menu-danger" disabled={deleting} onClick={() => {
            setMenuOpen(false);
            setDeleting(true);
            setDeleteError(null);
            void Promise.resolve().then(onDelete)
              .catch(() => setDeleteError("Sohbet silinemedi. Yeniden dene."))
              .finally(() => setDeleting(false));
          }} role="menuitem" type="button">Sil</button>}
        </div>, document.body)}
      </div>
      {deleteError && <span role="alert">{deleteError}</span>}
    </div>
  );
}

export function Sidebar({
  profileHost,
  collapsed = false,
  etkin,
  onNavigate = () => undefined,
  onSec,
  onSil,
  onMove,
  onProjectCreate,
  onProjectRename,
  onProjectDelete,
  onAssign,
  onPickFolder,
  onYeni,
  oturumlar,
  projeler = [],
  hesap = null,
  onCikis,
  guncellemeSurumu = null,
  onGuncellemeAc,
}: SidebarProps) {
  const [profileOpen, setProfileOpen] = useState(false);
  const [profileMoreOpen, setProfileMoreOpen] = useState(false);
  const profileRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [projectPreferences, setProjectPreferences] = useState(readProjectPreferences);
  const [projectMenu, setProjectMenu] = useState<string | null>(null);
  const [projectDialog, setProjectDialog] = useState<{ root: string; kind: "rename" | "remove"; recordId?: string } | null>(null);
  const [projectDraft, setProjectDraft] = useState("");
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [dialogBusy, setDialogBusy] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [createRoot, setCreateRoot] = useState<string | undefined>(undefined);
  const closeDialogs = () => {
    setProjectDialog(null);
    setCreateOpen(false);
    setCreateRoot(undefined);
    setDialogError(null);
  };
  /** Diyalog işlemi: hata diyalogda kalır, başarıda diyalog kapanır. */
  const runDialog = async (action: () => void | Promise<void>) => {
    setDialogBusy(true);
    setDialogError(null);
    try {
      await action();
      closeDialogs();
    } catch (error) {
      setDialogError(error instanceof Error ? error.message : String(error));
    } finally {
      setDialogBusy(false);
    }
  };
  // Proje satırı tıklanınca sohbetleri gösterir/gizler (Codex'teki gibi bir
  // akordeon); varsayılan AÇIK — kullanıcı kapattığı projeler burada tutulur.
  const [closedProjects, setClosedProjects] = useState<Set<string>>(new Set());
  const toggleProjectOpen = (root: string) => setClosedProjects((current) => {
    const next = new Set(current);
    if (next.has(root)) next.delete(root); else next.add(root);
    return next;
  });
  // "Projeler" başlığının "…" menüsü: gizlenmiş projeleri geri eklemek buraya
  // taşındı. Eskiden bu satırlar listede HER ZAMAN görünüyordu ve proje/sohbet
  // listesiyle karışıyordu.
  const [projectsMenuOpen, setProjectsMenuOpen] = useState(false);
  const projectsMenuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!projectsMenuOpen) return;
    const closeOnOutside = (event: MouseEvent) => {
      if (!projectsMenuRef.current?.contains(event.target as Node)) setProjectsMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setProjectsMenuOpen(false);
    };
    document.addEventListener("mousedown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [projectsMenuOpen]);
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
  const [agentsOpen, setAgentsOpen] = useState(false);
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
    const roots = [...projeler];
    for (const session of oturumlar) {
      if (!session.projectId && session.projectRoot && /\/Desktop\/?$/.test(session.projectRoot)
        && !roots.some((project) => !project.id && project.root === session.projectRoot)) {
        roots.push({ root: session.projectRoot, name: "Desktop", pinned: false, updated_at: session.updated_at ?? 0 });
      }
    }
    const available = roots
      .filter((project) => project.id || !projectPreferences[project.root]?.hidden)
      .map((project) => project.id ? project : ({
        ...project,
        name: projectPreferences[project.root]?.name || project.name,
        pinned: projectPreferences[project.root]?.pinned ?? project.pinned,
      }));
    const matches = normalized
      ? available.filter((project) =>
          `${project.name} ${project.root ?? ""}`.toLocaleLowerCase("tr").includes(normalized),
        )
      : available;
    return [...matches].sort((left, right) => {
      if (left.pinned !== right.pinned) return left.pinned ? -1 : 1;
      return right.updated_at - left.updated_at;
    });
  }, [projectPreferences, projeler, query, oturumlar]);
  const sessionGroups = useMemo(() => {
    const groups = new Map<string, { name: string; root?: string; id?: string; sessions: OturumSatiri[] }>();
    for (const project of filteredProjects) {
      groups.set(project.id ? `kayit:${project.id}` : project.root, { name: project.name, root: project.root, id: project.id, sessions: [] });
    }
    for (const session of filteredSessions) {
      const record = session.projectId ? filteredProjects.find((item) => item.id === session.projectId) : undefined;
      const project = record ?? filteredProjects.find((item) => !item.id && (session.projectRoot ? item.root === session.projectRoot : item.name === session.project));
      const looseName = !session.projectRoot && session.project !== "Desktop"
        ? session.project : undefined;
      const key = project?.id ? `kayit:${project.id}` : project?.root ?? looseName ?? "Sohbetler";
      if (!groups.has(key)) groups.set(key, { name: project?.name ?? looseName ?? "Sohbetler", root: project?.root, sessions: [] });
      groups.get(key)!.sessions.push(session);
    }
    for (const group of groups.values()) group.sessions.sort((a, b) => {
      const pinOrder = Number(pinnedSessions.includes(pinKey(b))) - Number(pinnedSessions.includes(pinKey(a)));
      return pinOrder || (b.updated_at ?? 0) - (a.updated_at ?? 0);
    });
    return [...groups.entries()];
  }, [filteredProjects, filteredSessions, pinnedSessions]);
  const hiddenProjects = projeler.filter((project) => !project.id && projectPreferences[project.root]?.hidden);
  const [projectInfo, setProjectInfo] = useState<{ key: string; name: string; root?: string; id?: string; count: number; top: number; left: number } | null>(null);
  const infoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const infoRef = useRef<HTMLDivElement>(null);
  const infoTrigger = useRef<HTMLButtonElement | null>(null);
  const cancelInfoClose = () => { if (infoTimer.current) clearTimeout(infoTimer.current); };
  const closeInfoSoon = () => { cancelInfoClose(); infoTimer.current = setTimeout(() => setProjectInfo(null), 180); };
  const showInfo = (element: HTMLElement, key: string, group: { name: string; root?: string; id?: string; sessions: OturumSatiri[] }) => {
    cancelInfoClose();
    infoTrigger.current = element.querySelector("button");
    const rect = element.getBoundingClientRect();
    setProjectInfo({ key, name: group.name, root: group.root, id: group.id, count: oturumlar.filter((session) => group.id ? session.projectId === group.id : !session.projectId && (session.projectRoot === group.root || (!session.projectRoot && session.project === group.name))).length, top: Math.max(8, Math.min(rect.top, window.innerHeight - 170)), left: Math.max(8, Math.min(rect.right + 8, window.innerWidth - 296)) });
  };
  useEffect(() => {
    const dismiss = (event: KeyboardEvent) => { if (event.key === "Escape") {
      cancelInfoClose();
      if (infoRef.current?.contains(document.activeElement)) infoTrigger.current?.focus();
      setProjectInfo(null);
    } };
    document.addEventListener("keydown", dismiss);
    return () => { document.removeEventListener("keydown", dismiss); cancelInfoClose(); };
  }, []);
  const renderSession = (session: OturumSatiri, group: { root?: string; id?: string } = {}) => (
    <SessionButton key={pinKey(session)} session={session} active={session.session_id === etkin}
      pinned={pinnedSessions.includes(pinKey(session))} onPin={() => togglePin(session)}
      onSelect={() => onSec(session.session_id)}
      onDelete={onSil ? async () => { await onSil(session.session_id); setPinnedSessions((current) => current.filter((key) => key !== pinKey(session))); } : undefined}
      onRemoveFromProject={onAssign && session.projectId ? () => onAssign(session.session_id, null) : undefined}
      moveTargets={[
        ...(onAssign ? filteredProjects.filter((project) => project.id && project.id !== (group.id ?? session.projectId)).map((project) => ({ key: `kayit:${project.id}`, name: project.name, run: () => onAssign(session.session_id, project.id!) })) : []),
        ...(onMove ? filteredProjects.filter((project) => !project.id && project.root !== (group.root ?? session.projectRoot)).map((project) => ({ key: project.root, name: project.name, run: () => onMove(session.session_id, project.root) })) : []),
      ]} />
  );

  useEffect(() => {
    if (!profileOpen) return;
    const closeOnOutside = (event: MouseEvent) => {
      if (!profileRef.current?.contains(event.target as Node)) {
        setProfileOpen(false);
        setProfileMoreOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setProfileOpen(false);
        setProfileMoreOpen(false);
      }
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
    setProfileMoreOpen(false);
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

  const profileFooter = (
      <div className="sidebar__bottom">
        {/* Güncelleme şeridi profilin HEMEN ÜSTÜNDE durur: kullanıcı yeni sürümü
            aramak zorunda kalmasın. Sürüm yoksa hiç çizilmez — boş bir satır
            "bir şey var mı?" sorusunu her açılışta yeniden sordururdu. */}
        {guncellemeSurumu && onGuncellemeAc && (
          <button aria-label={`${guncellemeSurumu} sürümü hazır`} title={`${guncellemeSurumu} sürümü hazır`} className="sidebar__update" onClick={onGuncellemeAc} type="button">
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
              <button onClick={() => navigateFromProfile("personalization")} role="menuitem" type="button"><Icon name="user" /><span>Kişiselleştirme</span></button>
              <button onClick={() => navigateFromProfile("account")} role="menuitem" type="button"><Icon name="user" /><span>Hesabım</span></button>
              <button onClick={() => navigateFromProfile("settings")} role="menuitem" type="button"><Icon name="settings" /><span>Ayarlar</span></button>
              <button onClick={() => navigateFromProfile("help")} role="menuitem" type="button"><Icon name="help" /><span>Yardım</span></button>
              <button onClick={() => navigateFromProfile("feedback")} role="menuitem" type="button"><Icon name="chat" /><span>Geri bildirim gönder</span></button>
              <button aria-expanded={profileMoreOpen} onClick={() => setProfileMoreOpen((open) => !open)} role="menuitem" type="button"><Icon name="panel" /><span>Daha fazla</span><Icon name="chevron" size={16} /></button>
              {profileMoreOpen && <div aria-label="Ek araçlar" className="sidebar__profile-more" role="group">
                <button onClick={() => navigateFromProfile("control-panel")} role="menuitem" type="button"><Icon name="panel" /><span>Kontrol Paneli</span></button>
                <button onClick={() => navigateFromProfile("skills")} role="menuitem" type="button"><Icon name="skills" /><span>Beceriler ve Ajanlar</span></button>
                <button onClick={() => navigateFromProfile("connectors")} role="menuitem" type="button"><Icon name="terminal" /><span>MCP bağlantıları</span></button>
                <button onClick={() => navigateFromProfile("language")} role="menuitem" type="button"><Icon name="lessons" /><span>Dil</span></button>
              </div>}
              <div className="sidebar__profile-separator" />
              {hesap
                ? <button onClick={() => { setProfileOpen(false); setProfileMoreOpen(false); onCikis?.(); }} role="menuitem" type="button"><Icon name="logout" /><span>Çıkış yap</span></button>
                : <button onClick={() => navigateFromProfile("account")} role="menuitem" type="button"><Icon name="logout" /><span>Giriş yap</span></button>}
            </div>
          )}
          <button
            aria-expanded={profileOpen}
            aria-haspopup="menu"
            aria-label={profileMenuLabel}
            title={profileName}
            className="sidebar__profile-trigger"
            onClick={() => { setProfileOpen((open) => !open); setProfileMoreOpen(false); }}
            type="button"
          >
            <span className="sidebar__avatar">{profileInitials}</span>
            <span className="sidebar__profile-copy sidebar__label"><strong>{profileName}</strong><small>{profileDetail}</small></span>
            <span aria-hidden="true" className="sidebar__profile-status" data-connected={Boolean(hesap)} />
          </button>
        </div>
      </div>
  );

  return (
    <nav aria-label="Fusion" className="sidebar" data-collapsed={collapsed}>
      <div aria-hidden="true" className="sidebar__titlebar-spacer" data-tauri-drag-region />
      <div className="sidebar__top">
        <div aria-label="Fusion" className="sidebar__brand">
          <Logo size={24} />
          <span className="sidebar__label fusion-wordmark">Fusion</span>
          <button aria-label="Konuşma ve proje aramasını aç" aria-expanded={searchOpen} className="sidebar__search-trigger" onClick={() => setSearchOpen((open) => !open)} type="button"><Icon name="search" size={19} /></button>
        </div>
        <NavItem icon="new" label="Yeni sohbet" onClick={onYeni} />
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
        <section aria-label="Sabitlenenler" className="sidebar__pinned">
          <h2 className="sidebar__section-title">Sabitlenenler</h2>
          {filteredSessions.filter((session) => pinnedSessions.includes(pinKey(session))).map((session) => renderSession(session))}
        </section>
        <section aria-label="Projeler" className="sidebar__history">
              <div className="sidebar__history-body">
                <div className="sidebar__projects-heading" ref={projectsMenuRef}>
                  <span>Projeler</span>
                  <span className="sidebar__projects-heading-actions">
                    <button
                      aria-expanded={projectsMenuOpen}
                      aria-haspopup="menu"
                      aria-label="Proje listesi seçenekleri"
                      onClick={() => setProjectsMenuOpen((open) => !open)}
                      type="button"
                    >···</button>
                    <button aria-label="Yeni proje" onClick={() => onProjectCreate ? (setProjectDraft(""), setDialogError(null), setCreateOpen(true)) : onNavigate("new-project")} type="button">+</button>
                  </span>
                  {projectsMenuOpen && (
                    <div aria-label="Proje listesi seçenekleri" className="sidebar__project-menu sidebar__projects-menu" role="menu">
                      {hiddenProjects.length === 0
                        ? <p className="sidebar__projects-menu-empty">Gizlenmiş proje yok.</p>
                        : hiddenProjects.map((project) => (
                          <button
                            key={project.root}
                            onClick={() => { updateProject(project.root, { hidden: false }); setProjectsMenuOpen(false); }}
                            role="menuitem"
                            type="button"
                          >{project.name} projesini geri ekle</button>
                        ))}
                    </div>
                  )}
                </div>
                {sessionGroups.map(([groupKey, group]) => {
                  const projectSessions = group.sessions.filter((session) => !pinnedSessions.includes(pinKey(session)));
                  const pk = group.id ?? (group.root || undefined);
                  const isOpen = !pk || !closedProjects.has(pk);
                  return (
                  <section aria-label={group.name} className="sidebar__section" key={groupKey}>
                    <h2 className="sidebar__section-title">{pk ? <span className="sidebar__project-row"
                      onMouseEnter={(event) => showInfo(event.currentTarget, pk, group)} onMouseLeave={closeInfoSoon}
                      onFocus={(event) => showInfo(event.currentTarget, pk, group)}
                      onKeyDown={(event) => { if (event.key === "ArrowRight" && infoRef.current) { event.preventDefault(); cancelInfoClose(); infoRef.current.querySelector("button")?.focus(); } }}
                      onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node) && !infoRef.current?.contains(event.relatedTarget as Node)) closeInfoSoon(); }}>
                      <button
                        aria-expanded={isOpen}
                        aria-label={`${group.name} projesini aç`}
                        className="sidebar__project"
                        onClick={() => toggleProjectOpen(pk)}
                        type="button"
                      >
                        <Icon name={isOpen ? "folderOpen" : "folder"} size={18} />
                        <span className="sidebar__label">{group.name}</span>
                      </button>
                      <button
                        aria-label={`${group.name} projesinde yeni sohbet başlat`}
                        className="sidebar__project-new-chat"
                        onClick={() => onNavigate(group.id ? `project-id:${group.id}` : `project:${group.root}`)}
                        type="button"
                      ><Icon name="new" size={15} /></button>
                      <button aria-expanded={projectMenu === pk} aria-label={`${group.name} için proje seçeneklerini aç`} className="sidebar__project-options" onClick={() => setProjectMenu(projectMenu === pk ? null : pk)} type="button">···</button>
                    </span> : group.name}</h2>
                    {pk && projectMenu === pk && <div aria-label={`${group.name} proje seçenekleri`} className="sidebar__project-menu" role="menu">
                      <button onClick={() => { setProjectDraft(group.name); setDialogError(null); setProjectDialog({ root: pk, kind: "rename", recordId: group.id }); setProjectMenu(null); }} role="menuitem" type="button">Projeyi yeniden adlandır</button>
                      {!group.id && <button onClick={() => { updateProject(group.root!, { pinned: !projectPreferences[group.root!]?.pinned }); setProjectMenu(null); }} role="menuitem" type="button">{projectPreferences[group.root!]?.pinned ? "Sabitlemeyi kaldır" : "Projeyi sabitle"}</button>}
                      <button onClick={() => { setDialogError(null); setProjectDialog({ root: pk, kind: "remove", recordId: group.id }); setProjectMenu(null); }} role="menuitem" type="button">Projeyi sil</button>
                    </div>}
                    {isOpen && (expandedGroups.has(groupKey) || query.trim() ? projectSessions : projectSessions.slice(0, 5)).map((session) => renderSession(session, group))}
                    {isOpen && projectSessions.length > 5 && !query.trim() && <button aria-label={`${group.name}: ${expandedGroups.has(groupKey) ? "Daha az göster" : "Daha fazla göster"}`} className="sidebar__more" onClick={() => setExpandedGroups((current) => { const next = new Set(current); if (next.has(groupKey)) next.delete(groupKey); else next.add(groupKey); return next; })} type="button">{expandedGroups.has(groupKey) ? "Daha az göster" : "Daha fazla göster"}</button>}
                  </section>
                  );
                })}
              </div>
          </section>
          <section aria-label="Diğer ajanlar" className="sidebar__agents">
            <button aria-expanded={agentsOpen} aria-controls="sidebar-other-agents" className="sidebar__history-toggle" onClick={() => setAgentsOpen((open) => !open)} type="button"><span>Diğer ajanlar</span><Icon name="chevron" size={15} /></button>
            {agentsOpen && <div id="sidebar-other-agents">{(["codex", "claude", "hermes"] as const).map((source) => {
              const label = source === "codex" ? "Codex" : source === "claude" ? "Claude" : "Hermes";
              return <button aria-label={`${label} geçmişi`} className="sidebar__nav-item" key={source} onClick={() => onNavigate(`resume:${source}`)} type="button"><SourceIcon source={source} /><span className="sidebar__label">{label}</span></button>;
            })}</div>}
          </section>
      </div>

      {projectInfo && createPortal(<div ref={infoRef} aria-label={`${projectInfo.name} proje bilgileri`} role="dialog" className="sidebar__project-info" style={{ top: projectInfo.top, left: projectInfo.left }} onMouseEnter={cancelInfoClose} onMouseLeave={closeInfoSoon} onFocus={cancelInfoClose} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) closeInfoSoon(); }}>
        <strong><Icon name="folder" size={18} />{projectInfo.name}</strong><span><Icon name="chat" size={18} />{projectInfo.count} sohbet</span>
        {projectInfo.root && <small title={projectInfo.root}><Icon name="folder" size={18} />{projectInfo.root.replace(/^\/Users\/[^/]+(?=\/|$)/, "~")}</small>}
        <button aria-label={`${projectInfo.name} projesini düzenle`} onClick={() => { setProjectDraft(projectInfo.name); setDialogError(null); setProjectDialog({ root: projectInfo.key, kind: "rename", recordId: projectInfo.id }); setProjectInfo(null); }} type="button"><Icon name="settings" size={18} />Projeyi düzenle</button>
      </div>, document.body)}

      {(projectDialog || createOpen) && <div className="sidebar__project-backdrop" role="presentation">
        <div aria-label={createOpen ? "Yeni proje" : projectDialog!.kind === "rename" ? "Projeyi yeniden adlandır" : "Projeyi sil"} aria-modal="true" className="sidebar__project-dialog" role="dialog">
          <h2>{createOpen ? "Yeni proje" : projectDialog!.kind === "rename" ? "Projeyi yeniden adlandır" : "Projeyi sil"}</h2>
          {(createOpen || projectDialog!.kind === "rename")
            ? <input aria-label="Proje adı" autoFocus maxLength={80} onChange={(event) => setProjectDraft(event.target.value)} placeholder="Proje adı" value={projectDraft} />
            : <p>{projectDialog!.recordId ? "Proje listeden kalkar. Sohbetler silinmez; Sohbetler altına geçer." : "Proje Fusion listesinden kaldırılır. Bilgisayarındaki klasörler ve sohbet kayıtları korunur."}</p>}
          {createOpen && onPickFolder && <div className="sidebar__project-folder">
            <button disabled={dialogBusy} onClick={() => void onPickFolder().then((root) => { if (root) setCreateRoot(root); }).catch(() => setDialogError("Klasör seçilemedi."))} type="button">Klasör seç</button>
            <small>{createRoot ?? "İsteğe bağlı; seçilmezse sohbetler Desktop içinde açılır."}</small>
          </div>}
          {dialogError && <p role="alert">{dialogError}</p>}
          <div><button onClick={closeDialogs} type="button">Vazgeç</button>{createOpen
            ? <button disabled={dialogBusy || !projectDraft.trim()} onClick={() => void runDialog(() => onProjectCreate!({ name: projectDraft.trim(), root: createRoot }))} type="button">Oluştur</button>
            : <button disabled={dialogBusy || (projectDialog!.kind === "rename" && !projectDraft.trim())} onClick={() => {
              const dialog = projectDialog!;
              if (dialog.recordId) {
                const id = dialog.recordId;
                void runDialog(() => dialog.kind === "rename" ? onProjectRename?.(id, projectDraft.trim()) : onProjectDelete?.(id));
                return;
              }
              updateProject(dialog.root, dialog.kind === "rename" ? { name: projectDraft.trim() } : { hidden: true });
              closeDialogs();
            }} type="button">{projectDialog!.kind === "rename" ? "Kaydet" : projectDialog!.recordId ? "Projeyi sil" : "Listeden kaldır"}</button>}</div>
        </div>
      </div>}

      {profileHost === undefined ? profileFooter : profileHost ? createPortal(profileFooter, profileHost) : null}
    </nav>
  );
}

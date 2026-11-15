import { useMobileNavigation } from './use-mobile-navigation';
import { createDurableConversation } from './conversation-create';
import { loadChatDraft, saveChatDraft } from './chat-draft';
import {
  bindScheduledThread,
  listenScheduledDelivery,
  type DeliveryBinding,
} from './scheduled-delivery-bridge';
import { FusionPanel } from './FusionPanel';
import { openPageLink } from './page-navigation';
import { SpaceNav } from './SpaceNav';
import { SpaceWorkspace } from './SpaceWorkspace';
import { useCallback, useEffect, useState, useRef } from 'react';
import { CopilotKitProvider } from '@copilotkit/react-core/v2';
import {
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  Clock3,
  Code2,
  Cpu,
  Folder,
  Menu,
  Monitor,
  MoreHorizontal,
  Pause,
  PanelLeft,
  Play,
  Plus,
  Search,
  Settings2,
  Trash2,
  X,
} from 'lucide-react';
import type {
  Conversation,
  Detail,
  Dot,
  Result,
  State,
  WorkspaceState,
} from '../shared/types';
import {
  api,
  ApiError,
  authHeaders,
  errorText,
  setToken,
  UNREACHABLE_MESSAGE,
} from './api';
import { Mascot } from './Mascot';
import { Chat } from './Chat';
import { ThreadList } from './ThreadList';
import { ResultPane } from './ResultPane';
import { TaskRow } from './TaskPresentation';
import { TaskActions } from './TaskActions';
import { WorkspaceDialog, type Dialog } from './WorkspaceDialog';
import { SLACK_STATUS } from './labels';

export function App() {
  const [state, setState] = useState<State>();
  const [workspace, setWorkspace] = useState<WorkspaceState>();
  const [selectedDot, setSelectedDot] = useState('');
  const [selectedThread, setSelectedThread] = useState<string>();
  const threadSelection = useRef<AbortController | null>(null);
  const [threadOpening, setThreadOpening] = useState(false);
  useEffect(() => () => threadSelection.current?.abort(), []);
  const [deliveryBinding, setDeliveryBinding] = useState<DeliveryBinding>();
  const bindingAttempt = useRef(0);
  useEffect(() => {
    if (!deliveryBinding || window.parent === window) return;
    let active = true;
    let stop: (() => void) | undefined;
    void listenScheduledDelivery(window, api, deliveryBinding)
      .then((cleanup) => {
        if (active) stop = cleanup;
        else cleanup();
      })
      .catch(() => {
        if (active)
          setError(
            'Host teslim bağlantısı kurulamadı; görevler beklemeye devam eder.',
          );
      });
    return () => {
      active = false;
      stop?.();
    };
  }, [deliveryBinding]);
  const [view, rawSetView] = useState<'chat' | 'tasks' | 'memories' | 'space'>(
    'chat',
  );
  const creation = useRef<AbortController | null>(null);
  const creationScope = useRef('');
  creationScope.current = JSON.stringify([
    workspace?.ownerId,
    selectedDot,
    selectedThread,
    view,
  ]);
  useEffect(() => () => creation.current?.abort(), []);
  const dirtyPage = useRef(false);
  const [spaceId, setSpaceId] = useState('');
  const [pageId, setPageId] = useState<string>();
  const setDirtyPage = useCallback((value: boolean) => {
    dirtyPage.current = value;
  }, []);
  const setView = (next: typeof view) => {
    if (
      dirtyPage.current &&
      !window.confirm('Kaydedilmemiş sayfa taslağından çıkılsın mı?')
    )
      return false;
    dirtyPage.current = false;
    creation.current?.abort();
    threadSelection.current?.abort();
    threadSelection.current = null;
    setThreadOpening(false);
    if (next !== 'space')
      history.replaceState(null, '', location.pathname + location.search);
    rawSetView(next);
    return true;
  };
  useEffect(() => {
    let acceptedHash = location.hash;
    const navigate = () => {
      const match = location.hash.match(
        /^#\/spaces\/([^/]+)(?:\/pages\/([^/]+))?$/,
      );
      if (!match) return;
      if (dirtyPage.current && location.hash === acceptedHash) return;
      if (
        dirtyPage.current &&
        !window.confirm('Kaydedilmemiş sayfa taslağından çıkılsın mı?')
      ) {
        history.replaceState(null, '', acceptedHash || location.pathname);
        return;
      }
      acceptedHash = location.hash;
      creation.current?.abort();
      threadSelection.current?.abort();
      threadSelection.current = null;
      setThreadOpening(false);
      dirtyPage.current = false;
      setSpaceId(match[1]);
      setPageId(match[2]);
      rawSetView('space');
      setMobile(false);
    };
    navigate();
    window.addEventListener('hashchange', navigate);
    return () => window.removeEventListener('hashchange', navigate);
  }, []);
  const openPage = (space: string, page?: string) => {
    openPageLink(`#/spaces/${space}${page ? `/pages/${page}` : ''}`);
  };

  const [error, setError] = useState('');
  const [auth, setAuth] = useState('');
  const [needsAuth, setNeedsAuth] = useState(false);
  const [dialog, rawSetDialog] = useState<Dialog>();
  const [mobile, setMobile] = useState(false);
  const setDialog = useCallback((next: Dialog | undefined) => {
    setMobile(false);
    rawSetDialog(next);
  }, []);
  const mobileNavigation = useMobileNavigation(mobile, setMobile);
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [pane, setPane] = useState(false);
  const [fusionPane, setFusionPane] = useState(false);
  const [capture, setCapture] = useState<Result>();
  const [prompt, setPrompt] = useState('');
  const [pendingPrompt, setPendingPrompt] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');
  const [taskDetail, setTaskDetail] = useState<Detail>();
  const refresh = useCallback(async () => {
    try {
      const [s, w] = await Promise.all([
        api<State>('/state'),
        api<WorkspaceState>('/workspace'),
      ]);
      setState(s);
      setWorkspace(w);
      setNeedsAuth(false);
      // Sunucu geri gelince kendiliğinden kalkar; başka hatalar kullanıcı kapatana dek kalır.
      setError((current) => (current === UNREACHABLE_MESSAGE ? '' : current));
      setSelectedDot((previous) => previous || w.dots[0]?.id || '');
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) setNeedsAuth(true);
      else setError(errorText(e, 'Sunucuya bağlanılamadı.'));
    }
  }, []);
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 3000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    setCapture(undefined);
    if (!selectedThread) return;
    let active = true;
    const load = () =>
      void api<Result | null>(`/conversations/${selectedThread}/capture`)
        .then((result) => {
          if (active) setCapture(result ?? undefined);
        })
        .catch((e) => {
          if (active) setError(errorText(e, 'Sonuç yüklenemedi.'));
        });
    load();
    const timer = setInterval(load, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [selectedThread]);
  const mutate = async (path: string, method: string, body?: unknown) => {
    setError('');
    try {
      await api(path, method, body);
      await refresh();
      if (taskDetail)
        setTaskDetail(await api<Detail>(`/tasks/${taskDetail.task.id}`));
      return true;
    } catch (e) {
      setError(errorText(e, 'Kaydedilemedi.'));
      return false;
    }
  };
  const dot =
    workspace?.dots.find((item) => item.id === selectedDot) ??
    workspace?.dots[0];
  const thread = workspace?.conversations.find(
    (item) => item.id === selectedThread && item.dotId === dot?.id,
  );
  const configured = !!workspace && workspace.setup.missing.length === 0;
  const bindDelivery = async () => {
    const attempt = ++bindingAttempt.current;
    try {
      const binding = await bindScheduledThread(
        api,
        thread?.id ?? '',
        dot?.fusionAllowed === true,
      );
      if (attempt === bindingAttempt.current) setDeliveryBinding(binding);
    } catch {
      if (attempt === bindingAttempt.current)
        setError(
          'Teslim bağı kurulamadı; Fusion izni ve proje kökünü kontrol edin.',
        );
    }
  };
  const clearDelivery = () => {
    bindingAttempt.current += 1;
    setDeliveryBinding(undefined);
  };
  const chooseDot = (next: Dot) => {
    setSelectedDot(next.id);
    setSelectedThread(
      workspace?.conversations.find((item) => item.dotId === next.id)?.id,
    );
    setView('chat');
    setMobile(false);
    setPendingPrompt(undefined);
  };
  const selectThread = async (id: string, dotId: string) => {
    if (!setView('chat')) return;
    const controller = new AbortController();
    threadSelection.current = controller;
    setThreadOpening(true);
    try {
      let selected = workspace?.conversations.find((item) => item.id === id);
      if (!selected)
        selected = await api<Conversation>(
          '/conversations/import',
          'POST',
          { id, dotId },
          controller.signal,
        );
      if (controller.signal.aborted || threadSelection.current !== controller)
        return;
      if (selected.id !== id || selected.dotId !== dotId)
        throw new Error('Sohbet kapsamı doğrulanamadı.');
      const accepted = selected;
      setWorkspace((previous) =>
        previous
          ? {
              ...previous,
              conversations: [
                ...previous.conversations.filter((item) => item.id !== id),
                accepted,
              ],
            }
          : previous,
      );
      setSelectedDot(dotId);
      setSelectedThread(id);
      setMobile(false);
    } catch (error) {
      if (!controller.signal.aborted && threadSelection.current === controller)
        setError(errorText(error, 'Sohbet açılamadı.'));
    } finally {
      if (threadSelection.current === controller) {
        threadSelection.current = null;
        setThreadOpening(false);
      }
    }
  };
  const newConversation = async (text?: string) => {
    if (!dot || !configured || busy || creation.current) return;
    const controller = new AbortController();
    creation.current = controller;
    const scope = creationScope.current;
    const current = () =>
      !controller.signal.aborted &&
      creation.current === controller &&
      creationScope.current === scope;
    const timer = setTimeout(() => controller.abort(), 45000);
    threadSelection.current?.abort();
    threadSelection.current = null;
    setThreadOpening(false);
    setBusy(true);
    setError('');
    try {
      const title = text?.slice(0, 80) || 'Yeni bir düşünce';
      const durable =
        workspace?.conversationRequestProtocol === 1 && workspace.ownerId
          ? await createDurableConversation({
              ownerId: workspace.ownerId,
              dotId: dot.id,
              title,
              storage: localStorage,
              createId: () => crypto.randomUUID(),
              call: (path, method, body) =>
                api(path, method, body, controller.signal),
            })
          : null;
      const next =
        durable?.conversation ??
        (await api<Conversation>(
          '/conversations',
          'POST',
          { dotId: dot.id, title },
          controller.signal,
        ));
      if (!current()) return;
      if (durable?.recovered && text) {
        const draft = loadChatDraft(next.id);
        if (draft.error) throw new Error(draft.error);
        if (!draft.text) {
          const error = saveChatDraft(
            next.id,
            text,
            draft.source,
            draft.submission,
          );
          if (error) throw new Error(error);
        } else if (draft.text !== text) {
          throw new Error(
            'Sohbet toparlandı; mevcut taslağı korumak için yeni metin bu ekranda bırakıldı.',
          );
        }
      }
      durable?.acknowledge();
      setWorkspace((previous) =>
        previous
          ? {
              ...previous,
              conversations: [
                ...previous.conversations.filter((item) => item.id !== next.id),
                next,
              ],
            }
          : previous,
      );
      setSelectedThread(next.id);
      setPendingPrompt(durable?.recovered ? undefined : text);
      setPrompt('');
      setView('chat');
      setMobile(false);
      if (durable?.recovered)
        setError(
          'Önceki sohbet toparlandı. Görev otomatik gönderilmedi; taslağı kontrol et.',
        );
    } catch (e) {
      if (current()) setError(errorText(e, 'Sohbet oluşturulamadı.'));
      else if (
        creation.current === controller &&
        creationScope.current === scope
      )
        setError(
          'Sohbet sonucu henüz doğrulanamadı. Aynı kabul korunuyor; tekrar deneyebilirsin.',
        );
    } finally {
      clearTimeout(timer);
      if (creation.current === controller) {
        creation.current = null;
        setBusy(false);
      }
    }
  };
  if (needsAuth)
    return (
      <main className="unlock">
        <Mascot />
        <h1>Kendi küçük köşen.</h1>
        <p>Bu şablonun sunucusunda ayarlanan sahip erişim anahtarını gir.</p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setToken(auth);
            try {
              await api('/state');
              setError('');
              await refresh();
            } catch (err) {
              setError(
                err instanceof Error
                  ? err.message
                  : 'Erişim anahtarı kabul edilmedi.',
              );
            }
          }}
        >
          <input
            type="password"
            aria-label="Sahip erişim anahtarı"
            autoComplete="current-password"
            value={auth}
            onChange={(e) => setAuth(e.target.value)}
            required
          />
          <button className="primary">Fusion Kits kilidini aç</button>
        </form>
        {error && (
          <p className="chat-error" role="alert">
            {error}
          </p>
        )}
        <p className="muted">
          Anahtar yalnızca bu sekmenin oturum belleğinde tutulur.
        </p>
      </main>
    );
  if (!state || !workspace || !dot)
    return (
      <main className="unlock">
        <Mascot state="working" />
        <h1>Kit’ler hazırlanıyor…</h1>
        {error && (
          <>
            <p className="chat-error">{error}</p>
            <button onClick={() => void refresh()}>Yeniden dene</button>
          </>
        )}
      </main>
    );
  const content = (
    <div
      className={`app template-app fusion-kits ${navCollapsed ? 'nav-collapsed' : ''}`}
    >
      <nav className="icon-rail" aria-label="Çalışma alanı gezintisi">
        <button
          className="rail-brand"
          aria-label="Fusion Kits ana sayfa"
          onClick={() => {
            setView('chat');
            setSelectedThread(undefined);
          }}
        >
          <img src="/fusion.svg" alt="" width={24} height={24} />
        </button>
        <button
          aria-label={navCollapsed ? 'Menüyü genişlet' : 'Menüyü daralt'}
          onClick={() => setNavCollapsed(!navCollapsed)}
        >
          <PanelLeft size={18} />
        </button>
        <button
          aria-label="Yeni sohbet"
          disabled={!configured}
          onClick={() => void newConversation()}
        >
          <Plus size={19} />
        </button>
        <button
          aria-label="Alanları aç"
          onClick={() => {
            if (workspace.spaces[0]) openPage(workspace.spaces[0].id);
          }}
        >
          <Folder size={18} />
        </button>
        <button aria-label="Etkinliği aç" onClick={() => setView('tasks')}>
          <Clock3 size={18} />
        </button>
        <button
          className="rail-settings"
          aria-label="Ayarları aç"
          onClick={() => setDialog({ type: 'settings' })}
        >
          <Settings2 size={18} />
        </button>
      </nav>
      {mobile && (
        <button
          className="nav-scrim"
          aria-label="Menüyü kapat"
          onClick={() => setMobile(false)}
        />
      )}
      <aside
        ref={mobileNavigation.navigation}
        role={mobile ? 'dialog' : undefined}
        aria-modal={mobile || undefined}
        aria-label={mobile ? 'Gezinme' : undefined}
        id="workspace-sidebar"
        className={`sidebar ${mobile ? 'open' : ''}`}
      >
        <button
          className="sidebar-close icon-button"
          aria-label="Gezinmeyi kapat"
          onClick={() => setMobile(false)}
        >
          <X size={20} />
        </button>
        <button
          className="wordmark"
          onClick={() => {
            setView('chat');
            setSelectedThread(undefined);
          }}
        >
          <img src="/fusion.svg" alt="" width={26} height={26} />
          Fusion Kits<span className="wordmark-dot">•</span>
        </button>
        <button
          className="new-chat nav-item"
          disabled={!configured}
          onClick={() => void newConversation()}
        >
          <Plus size={17} />
          <span>Yeni sohbet</span>
        </button>
        <div className="spaces-heading nav-label">
          Kit’ler
          <button
            className="icon-button"
            aria-label="Kit oluştur"
            onClick={() =>
              setDialog({ type: 'dot', spaceId: workspace.spaces[0].id })
            }
          >
            <Plus size={14} />
          </button>
        </div>
        <nav className="dots-nav" aria-label="Kits">
          {workspace.dots.map((item) => (
            <div className="dot-nav-row" key={item.id}>
              <button
                className={`dot-nav ${dot.id === item.id && view === 'chat' ? 'active' : ''}`}
                aria-current={
                  dot.id === item.id && view === 'chat' ? 'page' : undefined
                }
                onClick={() => chooseDot(item)}
              >
                <Mascot
                  identity={item.id}
                  character={item.character}
                  name={item.name}
                  small
                  decorative
                />
                <span>{item.name}</span>
              </button>
              <button
                className="icon-button dot-settings"
                aria-label={`${item.name} ayarlarını düzenle`}
                onClick={() =>
                  setDialog({ type: 'dot', dot: item, spaceId: item.spaceId })
                }
              >
                <MoreHorizontal size={15} />
              </button>
            </div>
          ))}
        </nav>
        <div className="spaces-heading nav-label">
          Alanlar
          <button
            className="icon-button"
            aria-label="Alan oluştur"
            onClick={() => setDialog({ type: 'space' })}
          >
            <Plus size={14} />
          </button>
        </div>
        <nav className="spaces-nav" aria-label="Alanlar">
          {workspace.spaces.map((space) => (
            <SpaceNav
              key={space.id}
              space={space}
              active={view === 'space' && spaceId === space.id}
              pageId={pageId}
              onOpen={(id) => openPage(space.id, id)}
            />
          ))}
        </nav>
        {configured ? (
          <ThreadList
            dotId={dot.id}
            dots={workspace.dots}
            local={workspace.conversations}
            selected={view === 'chat' ? selectedThread : undefined}
            onSelect={(id, dotId) => void selectThread(id, dotId)}
            onNew={() => void newConversation()}
          />
        ) : (
          <div className="sidebar-empty">
            Kalıcı sohbet için Ayarlar ve bağlantılar bölümünü yapılandırın.
          </div>
        )}
        <div className="sidebar-bottom">
          <button
            className={`nav-item ${view === 'tasks' ? 'active' : ''}`}
            onClick={() => {
              setView('tasks');
              setMobile(false);
            }}
          >
            <Clock3 size={17} />
            <span>Görevler ve etkinlik</span>
            <small>{state.tasks.length}</small>
          </button>
          <button
            className={`nav-item ${view === 'memories' ? 'active' : ''}`}
            onClick={() => {
              setView('memories');
              setMobile(false);
            }}
          >
            <BookOpen size={17} />
            <span>Bellek</span>
            <small>{state.memories.length}</small>
          </button>
          <button
            className="nav-item"
            onClick={() => setDialog({ type: 'settings' })}
          >
            <Settings2 size={17} />
            <span>Ayarlar ve bağlantılar</span>
          </button>
          <a
            className="nav-item"
            href="https://github.com/emirhhan/fusion-cli"
            target="_blank"
            rel="noreferrer"
          >
            <Code2 size={17} />
            <span>Fusion kaynakları</span>
            <ArrowUpRight size={13} />
          </a>
          <div className="version">
            FUSION KITS <span>v0.1</span>
          </div>
        </div>
      </aside>
      <div className="workspace" ref={mobileNavigation.workspace}>
        <header className="topbar">
          <button
            ref={mobileNavigation.trigger}
            className="mobile-menu icon-button"
            aria-label="Menüyü aç"
            aria-expanded={mobile}
            aria-controls="workspace-sidebar"
            onClick={() => setMobile(true)}
          >
            <Menu size={21} />
          </button>

          <button
            className="desktop-nav-toggle document-icon"
            aria-label={navCollapsed ? 'Menüyü göster' : 'Menüyü gizle'}
            onClick={() => setNavCollapsed(!navCollapsed)}
          >
            <PanelLeft size={18} />
          </button>
          <div className="breadcrumbs">
            <span>
              {view === 'space'
                ? workspace.spaces.find((space) => space.id === spaceId)?.name
                : 'Kits'}
            </span>
            <span>/</span>
            <strong>
              {view === 'chat'
                ? dot.name
                : view === 'tasks'
                  ? 'Etkinlik'
                  : view === 'space'
                    ? 'Sayfalar'
                    : 'Bellek'}
            </strong>
          </div>
          <div className="top-actions">
            <button
              className="icon-button"
              aria-label="Fusion çekirdeğini göster"
              aria-expanded={fusionPane}
              onClick={() => setFusionPane(!fusionPane)}
            >
              <Cpu size={18} />
            </button>
            {!configured && <span className="mode-badge">KURULUM GEREKLİ</span>}
            <button
              className="pause-button"
              aria-label={
                state.settings.paused
                  ? 'Tüm Kit’leri sürdür'
                  : 'Tüm Kit’leri duraklat'
              }
              onClick={() =>
                void mutate('/settings', 'PATCH', {
                  paused: !state.settings.paused,
                })
              }
            >
              {state.settings.paused ? <Play size={14} /> : <Pause size={14} />}
              <span>{state.settings.paused ? 'Sürdür' : 'Duraklat'}</span>
            </button>
            <button
              className="icon-button"
              aria-label={pane ? 'Bilgisayarı gizle' : 'Bilgisayarı göster'}
              aria-expanded={pane}
              onClick={() => setPane(!pane)}
            >
              <Monitor size={18} />
            </button>
          </div>
        </header>
        {window.parent !== window && (
          <section
            className="delivery-binding"
            aria-label="Zamanlanmış görev teslim bağı"
          >
            <button
              type="button"
              disabled={!thread || dot.fusionAllowed !== true}
              onClick={() => void bindDelivery()}
            >
              Bu konuşmaya zamanlanmış görevleri bağla
            </button>
            {deliveryBinding ? (
              <p role="status">
                Teslim bağı: {deliveryBinding.threadId} · {deliveryBinding.root}
                . Bu bağ görevlerin tamamlandığı anlamına gelmez.
                <button type="button" onClick={clearDelivery}>
                  Bağı kaldır
                </button>
              </p>
            ) : (
              <p role="status">Teslim bağı yok; zamanlanmış görevler bekler.</p>
            )}
          </section>
        )}
        {fusionPane && (
          <FusionPanel
            threadId={thread?.id}
            onClose={() => setFusionPane(false)}
          />
        )}
        {threadOpening && <p role="status">Sohbet açılıyor…</p>}
        {error && (
          <div className="error-banner" role="alert">
            <span>{error}</span>
            <button
              className="icon-button"
              aria-label="Hatayı kapat"
              onClick={() => setError('')}
            >
              <X size={16} />
            </button>
          </div>
        )}
        {state.settings.paused && (
          <div className="notice">
            Tüm Kit’ler duraklatıldı. Çalışan görevler durur, planlı işler
            bekler.
          </div>
        )}
        {view === 'space' ? (
          <SpaceWorkspace
            key={spaceId}
            space={
              workspace.spaces.find((s) => s.id === spaceId) ??
              workspace.spaces[0]
            }
            pageId={pageId}
            workspace={workspace}
            paused={state.settings.paused}
            onPage={(id) => openPage(spaceId, id)}
            onSettings={() => setDialog({ type: 'settings' })}
            onCreateDot={() => setDialog({ type: 'dot', spaceId })}
            onDirty={setDirtyPage}
            onRefresh={refresh}
            onSchedule={(threadId) => setDialog({ type: 'schedule', threadId })}
            onThread={(id) => {
              const target = workspace.conversations.find((t) => t.id === id);
              if (target) {
                setView('chat');
                setSelectedDot(target.dotId);
                setSelectedThread(id);
              }
            }}
          />
        ) : view === 'chat' ? (
          <div className={`chat-workspace ${pane ? 'split' : ''}`}>
            <div className="chat-column">
              {thread && configured ? (
                <Chat
                  key={thread.id}
                  thread={thread}
                  dot={dot}
                  initialPrompt={pendingPrompt}
                  onConsumed={() => setPendingPrompt(undefined)}
                  voiceReady={workspace.setup.voice}
                  voiceRealtime={workspace.setup.voiceRealtime}
                  calls={workspace.calls.filter(
                    (call) => call.threadId === thread.id,
                  )}
                  paused={state.settings.paused}
                  onSaved={refresh}
                  onComputer={() => setPane(true)}
                  onSchedule={() =>
                    setDialog({ type: 'schedule', threadId: thread.id })
                  }
                />
              ) : (
                <div className="new-conversation">
                  <div className="empty-chat-persona">
                    <Mascot
                      identity={dot.id}
                      character={dot.character}
                      name={dot.name}
                      state={state.settings.paused ? 'paused' : 'idle'}
                    />
                    <h1>{dot.name} ile ne üzerinde çalışalım?</h1>
                  </div>
                  {!configured && (
                    <div className="setup-card">
                      <span className="setup-icon">
                        <Settings2 size={20} />
                      </span>
                      <div>
                        <strong>Kit bağlantılarını kur</strong>
                        <p>
                          Sohbete başlamak için Ayarlar’dan modelini ve sohbet
                          hizmetini bağla. Alanların ve Kit tercihlerin
                          kullanıma hazır.
                        </p>
                      </div>
                    </div>
                  )}
                  <form
                    className="composer"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void newConversation(prompt);
                    }}
                  >
                    <textarea
                      aria-label="Sohbet başlat"
                      placeholder={
                        configured
                          ? 'İstediğin bir şeyi sor'
                          : 'İlk sohbetin kurulumdan sonra başlar.'
                      }
                      rows={1}
                      value={prompt}
                      maxLength={4000}
                      onChange={(e) => setPrompt(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          e.currentTarget.form?.requestSubmit();
                        }
                      }}
                      disabled={!configured}
                    />
                    <div className="composer-bottom">
                      <button
                        type="button"
                        className="composer-chip"
                        onClick={() =>
                          setDialog({ type: 'dot', dot, spaceId: dot.spaceId })
                        }
                      >
                        {dot.name}
                      </button>
                      <button
                        className="send-button"
                        aria-label="Sohbeti başlat"
                        disabled={!configured || busy || !prompt.trim()}
                      >
                        <ArrowUp size={19} />
                      </button>
                    </div>
                  </form>
                  <div className="starter-suggestions">
                    {[
                      'Düşünmeme yardım et',
                      'Herkese açık bir sayfayı araştır',
                      'Takip edebileceğim bir plan yap',
                    ].map((text) => (
                      <button
                        key={text}
                        disabled={!configured}
                        onClick={() => setPrompt(text)}
                      >
                        {text}
                      </button>
                    ))}
                  </div>
                  <div className="connection-note">
                    <span
                      className={`online-dot ${workspace.setup.slack === 'online' ? '' : 'off'}`}
                    />
                    Slack ·{' '}
                    {SLACK_STATUS[workspace.setup.slack] ??
                      workspace.setup.slack}
                    <button
                      className="text-button"
                      onClick={() => setDialog({ type: 'settings' })}
                    >
                      Kurulum ayrıntıları
                    </button>
                  </div>
                </div>
              )}
            </div>
            {pane && (
              <ResultPane
                key={dot.id}
                dots={workspace.dots}
                defaultDotId={dot.id}
                latest={capture}
                dotState="idle"
                onClose={() => setPane(false)}
              />
            )}
          </div>
        ) : (
          <main className="main-content">
            <div className="page-heading">
              <div>
                <span className="eyebrow">ÇALIŞMA ALANIN</span>
                <h1>{view === 'memories' ? 'Bellek' : 'Küçük bir takip.'}</h1>
                <p>
                  {view === 'memories'
                    ? 'Kit’lerinle paylaşmayı seçtiğin tercihler.'
                    : 'Zamanlanmış turlar sunucuda kendi sohbetlerinde çalışır.'}
                </p>
              </div>
              {view === 'memories' && (
                <button
                  className="primary"
                  onClick={() => setDialog({ type: 'memory' })}
                >
                  <Plus size={15} />
                  Bellek ekle
                </button>
              )}
            </div>
            {view === 'memories' ? (
              <>
                <div className="memory-grid">
                  {state.memories.map((memory) => (
                    <article className="memory-card" key={memory.id}>
                      <BookOpen size={18} />
                      <p>{memory.text}</p>
                      <div>
                        <small>
                          {state.settings.memoryAllowed
                            ? 'İzin verilen Kit’lerde kullanılabilir'
                            : 'Bellek kullanımı kapalı'}
                        </small>
                        <button
                          className="icon-button"
                          aria-label="Belleği düzenle"
                          onClick={() => setDialog({ type: 'memory', memory })}
                        >
                          <MoreHorizontal size={17} />
                        </button>
                        <button
                          className="icon-button"
                          aria-label="Belleği sil"
                          onClick={() =>
                            void mutate(`/memories/${memory.id}`, 'DELETE', {})
                          }
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
                {!state.memories.length && (
                  <div className="large-empty">
                    <Mascot identity={dot.id} character={dot.character} />
                    <h2>Küçük bir bağlam çok işe yarar.</h2>
                    <p>
                      “Araştırma özetlerimi kısa tut.” gibi bir tercih ekle.
                      İstediğin zaman değiştirebilir veya kaldırabilirsin.
                    </p>
                  </div>
                )}
              </>
            ) : (
              <>
                <label className="search-box">
                  <Search size={16} />
                  <input
                    aria-label="Görevlerde ara"
                    placeholder="Görev bul…"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </label>
                <div className="task-list">
                  {state.tasks
                    .filter((task) =>
                      task.prompt.toLowerCase().includes(search.toLowerCase()),
                    )
                    .map((task) => (
                      <TaskRow
                        key={task.id}
                        task={task}
                        onClick={() =>
                          void api<Detail>(`/tasks/${task.id}`)
                            .then(setTaskDetail)
                            .catch((e) =>
                              setError(errorText(e, 'İşlem başarısız oldu.')),
                            )
                        }
                      />
                    ))}
                </div>
                {!state.tasks.length && (
                  <div className="large-empty">
                    <Clock3 size={32} />
                    <h2>Bir düşünce sana geri dönsün.</h2>
                    <p>
                      Bir sohbet aç ve saat düğmesiyle sunucu tarafında
                      çalışacak bir görev planla.
                    </p>
                  </div>
                )}
                {taskDetail && (
                  <section className="task-detail-card">
                    <h2>{taskDetail.task.prompt}</h2>
                    <TaskActions
                      task={taskDetail.task}
                      busy={busy}
                      settings={state.settings}
                      onAction={(action) =>
                        void mutate(
                          `/tasks/${taskDetail.task.id}/actions`,
                          'POST',
                          { action },
                        )
                      }
                      onSchedule={async () => {
                        const raw = window.prompt(
                          'Tekrar aralığı (dakika; 0 planı kaldırır)',
                          String((taskDetail.task.intervalSeconds ?? 0) / 60),
                        );
                        if (raw === null) return;
                        const value = Number(raw);
                        if (!Number.isFinite(value) || value < 0) {
                          setError('Geçerli bir dakika sayısı gir.');
                          return;
                        }
                        await mutate(
                          `/tasks/${taskDetail.task.id}/schedule`,
                          'PUT',
                          {
                            intervalSeconds: value
                              ? Math.round(value * 60)
                              : null,
                          },
                        );
                      }}
                    />
                    {taskDetail.task.error && (
                      <p className="chat-error">{taskDetail.task.error}</p>
                    )}
                    {taskDetail.events.slice(-6).map((event) => (
                      <p className="muted" key={event.id}>
                        {event.text}
                      </p>
                    ))}
                    <small>{taskDetail.runs.length} kayıtlı çalıştırma</small>
                  </section>
                )}
              </>
            )}
          </main>
        )}
        {pane && view !== 'chat' && (
          <div className="computer-overlay">
            <ResultPane
              key={view === 'space' ? spaceId : dot.id}
              dots={workspace.dots}
              defaultDotId={
                view === 'space'
                  ? (workspace.dots.find((candidate) =>
                      candidate.spaceIds.includes(spaceId),
                    )?.id ?? dot.id)
                  : dot.id
              }
              dotState="idle"
              onClose={() => setPane(false)}
            />
          </div>
        )}
      </div>
      {dialog && (
        <WorkspaceDialog
          dialog={dialog}
          state={state}
          workspace={workspace}
          onClose={() => setDialog(undefined)}
          mutate={mutate}
        />
      )}
    </div>
  );
  return configured ? (
    <CopilotKitProvider
      runtimeUrl="/api/copilotkit"
      headers={authHeaders()}
      enableInspector={false}
      showDevConsole={false}
    >
      {content}
    </CopilotKitProvider>
  ) : (
    content
  );
}

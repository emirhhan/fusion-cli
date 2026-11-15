import { loadChatDraft, saveChatDraft } from './chat-draft';
import { AssetAttachments } from './AssetAttachments';
import { FusionPanel } from './FusionPanel';
import { PageReviewCard } from './PageReviewCard';
import { pageReviewSchema, pageReviewTool } from '../shared/page-review';
import {
  localComputerSchema,
  localComputerTool,
} from '../shared/local-computer';
import { requestLocalComputer } from './local-computer-bridge';
import {
  FUSION_BROWSER_NOT_ALLOWED,
  fusionBrowserSchema,
  fusionBrowserTool,
} from '../shared/fusion-browser';
import { requestFusionBrowser } from './fusion-browser-bridge';
import { requestFusionProfile } from './fusion-profile-bridge';
import {
  fusionProfileSchema,
  fusionProfileTool,
} from '../shared/fusion-profile';
import { contextualMessage, type PageContext } from './page-context';
import { api, errorText } from './api';
import type { Page } from '../server/pages';
import { useEffect, useRef, useState } from 'react';
import {
  CopilotChatToolCallsView,
  useRenderTool,
  useHumanInTheLoop,
  useFrontendTool,
  useAgent,
  useCopilotKit,
} from '@copilotkit/react-core/v2';
import {
  FilePlus,
  ArrowUp,
  Clock3,
  Link2,
  Phone,
  PhoneOff,
  Square,
  X,
} from 'lucide-react';
import {
  ComputerToolCard,
  type ComputerToolRenderProps,
} from './ComputerToolCard';
import { ChatTranscript, isInternalVoiceReceipt } from './ChatTranscript';
import type { CallReceipt, Conversation, Dot } from '../shared/types';
import { Mascot } from './Mascot';
import { useVoice } from './useVoice';
import { useLocalVoice } from './local-voice/useLocalVoice';
import { CallView } from './CallView';
export function Chat({
  thread,
  dot,
  initialPrompt,
  onConsumed,
  voiceReady,
  voiceRealtime = false,
  calls,
  paused,
  onSaved,
  onSchedule,
  onComputer,
}: {
  thread: Conversation;
  dot: Dot;
  initialPrompt?: string;
  onConsumed: () => void;
  voiceReady: boolean;
  /** OpenAI Realtime yapılandırılmışsa o kullanılır; yoksa yerel ses. */
  voiceRealtime?: boolean;
  calls: CallReceipt[];
  paused: boolean;
  onSaved: () => void;
  onSchedule: () => void;
  onComputer?: () => void;
}) {
  const { agent, isReady } = useAgent({
    agentId: `chat-${thread.id}`,
    runtimeAgentId: dot.id,
    threadId: thread.id,
  });
  const { copilotkit } = useCopilotKit();
  const [pageContext, setPageContext] = useState<PageContext | null>();
  const [contextError, setContextError] = useState('');
  const [contextAttempt, setContextAttempt] = useState(0);
  const contextReady = pageContext !== undefined;
  useEffect(() => {
    let active = true;
    setPageContext(undefined);
    setContextError('');
    void api<PageContext | null>(
      `/conversations/${thread.id}/page-context`,
      'GET',
      undefined,
      AbortSignal.timeout(10000),
    )
      .then((page) => {
        if (active) setPageContext(page);
      })
      .catch(() => {
        if (active)
          setContextError(
            'Sohbet bağlamı yüklenemedi. Mesajını göndermeden önce yeniden dene.',
          );
      });
    return () => {
      active = false;
    };
  }, [thread.id, contextAttempt]);
  const [restoredDraft] = useState(() => loadChatDraft(thread.id));
  const retainedSubmission = useRef(restoredDraft.submission);
  const lifecycle = useRef({
    mounted: false,
    epoch: 0,
    observers: new Set<{ unsubscribe(): void }>(),
  });
  useEffect(() => {
    const owner = lifecycle.current;
    owner.mounted = true;
    owner.epoch += 1;
    return () => {
      owner.mounted = false;
      owner.epoch += 1;
      for (const observer of owner.observers) observer.unsubscribe();
      owner.observers.clear();
    };
  }, [thread.id]);
  const [draft, setDraft] = useState(restoredDraft.text);
  const [source, setSource] = useState(restoredDraft.source);
  const draftCurrent = useRef(draft);
  const sourceCurrent = useRef(source);
  draftCurrent.current = draft;
  sourceCurrent.current = source;
  const [sourceOpen, setSourceOpen] = useState(Boolean(restoredDraft.source));
  const [error, setError] = useState(restoredDraft.error ?? '');
  useEffect(() => {
    const failure = saveChatDraft(thread.id, draft, source);
    if (failure) setError(failure);
  }, [thread.id, draft, source]);
  const [loaded, setLoaded] = useState(false);
  const [running, setRunning] = useState(false);
  const submitting = useRef(false);
  const realtimeVoice = useVoice(thread.id, onSaved, agent.messages.at(-1)?.id);
  // Sesli söz sunucuda normal bir sohbet turu olarak çalışır; döküm sohbete
  // yansısın diye her cevaptan sonra konuşma yeniden yüklenir.
  const localVoice = useLocalVoice(thread.id, () => {
    onSaved();
    // Bağlanma geçmişi baştan oynatır; liste boşaltılmazsa metinler üst üste
    // eklenip cevap ekranda iki-üç kez görünüyordu (kayıt doğruydu).
    agent.setMessages([]);
    void copilotkit.connectAgent({ agent }).catch(() => undefined);
  });
  const voice = voiceRealtime ? realtimeVoice : localVoice;
  const sent = useRef(false);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const subscription = copilotkit.subscribe({
      onError: ({ error }) => setError(errorText(error, 'Kit yanıt veremedi.')),
    });
    const events = agent.subscribe({
      onRunErrorEvent: ({ event }) => setError(event.message),
    });
    return () => {
      subscription.unsubscribe();
      events.unsubscribe();
    };
  }, [agent, copilotkit]);
  useEffect(() => {
    if (!isReady) return;
    let active = true;
    void copilotkit
      .connectAgent({ agent })
      .then(() => {
        if (active) setLoaded(true);
      })
      .catch((e) => {
        if (active) setError(errorText(e, 'Sohbet bağlantısı kurulamadı.'));
      });
    return () => {
      active = false;
    };
  }, [agent, copilotkit, isReady]);
  const send = async (text: string, observe = false) => {
    if (
      !text.trim() ||
      submitting.current ||
      running ||
      !loaded ||
      !contextReady ||
      paused
    )
      return;
    const epoch = lifecycle.current.epoch;
    const ownsView = () =>
      lifecycle.current.mounted && lifecycle.current.epoch === epoch;
    const prior = retainedSubmission.current;
    if (prior && !observe && (prior.text !== text || prior.source !== source)) {
      setError(
        'Önceki gönderimin sonucu belirsiz. Önce kayıtlı gönderimi yeniden sorgula.',
      );
      return;
    }
    const submission = prior ?? { runId: crypto.randomUUID(), text, source };
    const storageError = saveChatDraft(
      thread.id,
      observe ? draft : draft || text,
      source,
      submission,
    );
    if (storageError) {
      setError(storageError);
      return;
    }
    retainedSubmission.current = submission;
    submitting.current = true;
    setError('');
    setRunning(true);
    if (
      !agent.messages.some(
        (message) => message.id === `${submission.runId}:user`,
      )
    )
      agent.addMessage({
        id: `${submission.runId}:user`,
        role: 'user',
        content: contextualMessage(text, pageContext),
      });
    const draftSnapshot = draft;
    const sourceSnapshot = source;
    let terminalCompleted = false;
    const terminalObserver = agent.subscribe({
      onRunFinishedEvent: ({ event, outcome }) => {
        if (
          ownsView() &&
          event.runId === submission.runId &&
          event.threadId === thread.id &&
          outcome === 'success'
        )
          terminalCompleted = true;
      },
    });
    lifecycle.current.observers.add(terminalObserver);
    try {
      const result = await copilotkit.runAgent({
        agent,
        runId: submission.runId,
      });
      if (!ownsView()) return;
      if (
        !terminalCompleted &&
        !result.newMessages.some((message) => message.role === 'assistant')
      )
        throw new Error(
          'Bu tur yanıt döndürmedi. Çalışma ortamı bağlantısını kontrol edip yeniden dene.',
        );
      retainedSubmission.current = null;
      const persistedError = saveChatDraft(
        thread.id,
        !observe && draftCurrent.current === draftSnapshot
          ? ''
          : draftCurrent.current,
        !observe && sourceCurrent.current === sourceSnapshot
          ? ''
          : sourceCurrent.current,
        null,
      );
      if (persistedError) setError(persistedError);
      if (!observe)
        setDraft((current) => (current === draftSnapshot ? '' : current));
      if (!observe)
        setSource((current) => (current === sourceSnapshot ? '' : current));
      if (!observe) setSourceOpen(false);
      onSaved();
    } catch (e) {
      if (ownsView())
        setError(errorText(e, 'Tur başarısız oldu. Sohbetin kayıtlı kalıyor.'));
    } finally {
      terminalObserver.unsubscribe();
      lifecycle.current.observers.delete(terminalObserver);
      if (ownsView()) {
        submitting.current = false;
        setRunning(false);
      }
    }
  };
  useEffect(() => {
    if (loaded && contextReady && !paused && initialPrompt && !sent.current) {
      sent.current = true;
      onConsumed();
      void send(initialPrompt);
    }
  }, [loaded, contextReady, paused, initialPrompt]);
  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: 'instant', block: 'end' });
  }, [agent.messages.length, running]);
  useEffect(() => {
    if (paused && voice.status !== 'idle') void voice.end();
  }, [paused]);
  useHumanInTheLoop(
    {
      name: pageReviewTool.name,
      description: pageReviewTool.description,
      parameters: pageReviewSchema,
      render: (props) => (
        <PageReviewCard {...props} threadId={thread.id} onSaved={onSaved} />
      ),
    },
    [thread.id, onSaved],
  );
  // Kullanıcının kendi Mac'ine salt okunur bakış: izin her çağrıda Fusion'da sorulur.
  useFrontendTool(
    {
      name: localComputerTool.name,
      description: localComputerTool.description,
      parameters: localComputerSchema,
      handler: async ({ reason }) => requestLocalComputer(window, api, reason),
    },
    [],
  );
  // Kullanıcının gerçek Chrome'u (Fusion eklentisi): her istek Fusion'da onaylanır (P-063).
  // Yalnız Fusion izni açık Kit'ler kullanır; pencerede Kit'in adı görünür.
  useFrontendTool(
    {
      name: fusionBrowserTool.name,
      description: fusionBrowserTool.description,
      parameters: fusionBrowserSchema,
      handler: async (input) =>
        dot.fusionAllowed === true
          ? requestFusionBrowser(window, api, input, {
              kit: { id: dot.id, name: dot.name },
            })
          : {
              status: 'denied' as const,
              text: FUSION_BROWSER_NOT_ALLOWED,
            },
    },
    [dot.id, dot.name, dot.fusionAllowed],
  );
  // Fusion tarayıcı profilini Kit'in kendi tarayıcısına yükle (P-023): her istek Fusion'da
  // Kit adı, profil ve alan adlarıyla onaylanır; oturum bellek içi, model değerleri görmez.
  useFrontendTool(
    {
      name: fusionProfileTool.name,
      description: fusionProfileTool.description,
      parameters: fusionProfileSchema,
      handler: async (input) =>
        dot.fusionAllowed === true
          ? requestFusionProfile(window, api, dot.id, input, {
              kit: { id: dot.id, name: dot.name },
            })
          : {
              status: 'denied' as const,
              text: FUSION_BROWSER_NOT_ALLOWED,
            },
    },
    [dot.id, dot.name, dot.fusionAllowed],
  );
  const computerCalls = agent.messages.flatMap((message) =>
    message.role === 'assistant' ? (message.toolCalls ?? []) : [],
  );
  const latestBrowserCall = computerCalls.findLast((call) =>
    [
      'navigate',
      'snapshot',
      'read',
      'screenshot',
      'click',
      'type',
      'key',
      'scroll',
    ].some((action) => call.function.name === `computer_${action}`),
  );
  useRenderTool(
    {
      name: '*',
      render: (props: ComputerToolRenderProps) =>
        props.name.startsWith('computer_') ? (
          <ComputerToolCard
            {...props}
            dotId={dot.id}
            dotName={dot.name}
            running={running}
            showScreen={props.toolCallId === latestBrowserCall?.id}
            onExpand={onComputer}
          />
        ) : null,
    },
    [dot.id, dot.name, running, latestBrowserCall?.id, onComputer],
  );
  const visible = agent.messages.filter(
    (message) =>
      !isInternalVoiceReceipt(message) &&
      ['user', 'assistant'].includes(message.role) &&
      ((typeof message.content === 'string' && message.content.trim()) ||
        (message.role === 'assistant' &&
          message.toolCalls?.some(
            (call) =>
              call.function.name.startsWith('computer_') ||
              call.function.name === pageReviewTool.name,
          ))),
  );
  return (
    <div className="live-chat">
      <FusionPanel threadId={thread.id} embedded />
      <header className="chat-persona">
        <Mascot
          identity={dot.id}
          character={dot.character}
          name={dot.name}
          small
          state={running ? 'working' : paused ? 'paused' : 'idle'}
        />
        <div>
          <strong>{dot.name}</strong>
          <span>
            {paused
              ? 'Duraklatıldı'
              : running
                ? 'Düşünüyor…'
                : loaded && contextReady
                  ? 'Seninle'
                  : 'Sohbetine bağlanıyor…'}
          </span>
        </div>
        <div className="chat-persona-actions">
          <button
            className="icon-button"
            aria-label="Sohbeti sayfa olarak kaydet"
            disabled={running}
            onClick={async () => {
              const title = window.prompt('Sayfa başlığı', thread.title);
              if (!title) return;
              try {
                const page = await api<Page>(
                  `/conversations/${thread.id}/page`,
                  'POST',
                  { title },
                );
                location.hash = `/spaces/${page.spaceId}/pages/${page.id}`;
              } catch (e) {
                setError(errorText(e, 'Sohbet kaydedilemedi.'));
              }
            }}
          >
            <FilePlus size={18} />
          </button>
          <button
            className="icon-button"
            aria-label="Bu sohbette görev planla"
            onClick={onSchedule}
          >
            <Clock3 size={18} />
          </button>
          <button
            className={`icon-button ${voice.status === 'active' ? 'on-call' : ''}`}
            aria-label={
              voice.status === 'idle'
                ? 'Sesli aramayı başlat'
                : 'Sesli aramayı bitir'
            }
            title={
              voiceReady
                ? 'Kit’inle sesli konuş'
                : 'Sesli konuşma için önce sohbet kurulumunu tamamla'
            }
            disabled={!voiceReady || paused || !loaded || !contextReady}
            onClick={() =>
              voice.status === 'idle' ? void voice.start() : void voice.end()
            }
          >
            {voice.status === 'idle' ? (
              <Phone size={18} />
            ) : (
              <PhoneOff size={18} />
            )}
          </button>
        </div>
      </header>
      {pageContext && (
        <div className="page-chat-context">
          Üzerinde çalışılan:{' '}
          <a href={`/#/spaces/${pageContext.spaceId}/pages/${pageContext.id}`}>
            {pageContext.title}
          </a>
        </div>
      )}
      <div className="chat-transcript">
        {!visible.length && (
          <div className="chat-welcome">
            <h1>{dot.name} ile ne üzerinde çalışalım?</h1>
            <p className="muted">
              Sohbetin bu Kit’le kalır; yazıda da sesli konuşmada da.
            </p>
          </div>
        )}
        <ChatTranscript
          messages={visible}
          calls={calls}
          renderTools={(message) => (
            <CopilotChatToolCallsView
              message={message}
              messages={agent.messages}
            />
          )}
        />
        {running && (
          <div className="thinking">
            <span />
            <span />
            <span />
            <span>{dot.name} düşünüyor</span>
          </div>
        )}
        <div ref={bottom} />
      </div>
      {contextError && (
        <div className="chat-error" role="alert">
          {contextError}
          <button onClick={() => setContextAttempt((value) => value + 1)}>
            Bağlamı yeniden dene
          </button>
        </div>
      )}
      {(error || voice.error) && (
        <div className="chat-error" role="alert">
          {error || voice.error}
          {error && (
            <button
              onClick={() => {
                setError('');
                void copilotkit
                  .connectAgent({ agent })
                  .then(() => setLoaded(true))
                  .catch((e) => setError(errorText(e, 'Bağlanılamadı.')));
              }}
            >
              Yeniden bağlan
            </button>
          )}
        </div>
      )}
      <CallView
        key={voice.status === 'idle' ? 'idle' : 'call'}
        dot={dot}
        voice={voice}
      />
      {retainedSubmission.current && (
        <button
          type="button"
          disabled={running}
          aria-label="Kayıtlı gönderimin sonucunu sorgula"
          onClick={() => {
            const snapshot = retainedSubmission.current;
            if (snapshot) void send(snapshot.text, true);
          }}
        >
          Kayıtlı gönderimin sonucunu sorgula
        </button>
      )}
      <form
        className="chat-composer"
        onSubmit={(e) => {
          e.preventDefault();
          void send(`${source ? `Kaynak: ${source}\n\n` : ''}${draft}`);
        }}
      >
        <AssetAttachments
          scope={JSON.stringify([thread.id, dot.id])}
          content={draft}
          onInsert={(markdown) =>
            setDraft((current) => `${current.trimEnd()}\n\n${markdown}`)
          }
        />
        {sourceOpen && (
          <div className="source-input">
            <Link2 size={15} />
            <input
              aria-label="Kaynak sayfa adresi"
              type="url"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              placeholder="https://example.com/page"
            />
            <button
              type="button"
              className="icon-button"
              aria-label="Kaynağı kaldır"
              onClick={() => {
                setSourceOpen(false);
                setSource('');
              }}
            >
              <X size={14} />
            </button>
          </div>
        )}
        <div className="chat-compose-row">
          <button
            type="button"
            className="icon-button"
            aria-label="Kaynak sayfa bağlantısı ekle"
            onClick={() => setSourceOpen(!sourceOpen)}
          >
            <Link2 size={19} />
          </button>
          <textarea
            aria-label="Kit’ine mesaj yaz"
            placeholder={'İstediğin bir şeyi sor'}
            rows={1}
            value={draft}
            maxLength={4000}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
          />
          {running ? (
            <button
              type="button"
              className="send-button"
              aria-label="Yanıtı durdur"
              onClick={() => copilotkit.stopAgent({ agent })}
            >
              <Square size={16} />
            </button>
          ) : (
            <button
              className="send-button"
              aria-label="Mesaj gönder"
              disabled={!draft.trim() || !loaded || !contextReady || paused}
            >
              <ArrowUp size={19} />
            </button>
          )}
        </div>
        <div className="chat-compose-note">
          {voiceReady
            ? 'Yazı ve ses, tek bir sohbet.'
            : 'Yazı hazır. Ses, sohbet kurulumu bitince açılır.'}
        </div>
      </form>
    </div>
  );
}

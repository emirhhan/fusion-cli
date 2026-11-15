import { useCallback, useEffect, useRef, useState } from 'react';
import type { Dot } from '../shared/types';
import type { ComputerAction, ComputerStatus } from '../shared/computer-types';
import { api } from './api';
import {
  FrameRecorder,
  framesToGif,
  MAX_RECORDING_FRAMES,
  pollDelay,
} from './computer-recording';

type Screen = {
  base64: string;
  width: number;
  height: number;
  url: string;
  capturedAt: number;
};

const TAB_LABELS = {
  Browser: 'Tarayıcı',
  Files: 'Dosyalar',
  Terminal: 'Terminal',
  Activity: 'Etkinlik',
} as const;
const STATE_LABELS: Record<string, string> = {
  not_configured: 'yapılandırılmadı',
  stopped: 'durdu',
  running: 'çalışıyor',
  unavailable: 'kullanılamıyor',
};
const ACTOR_LABELS: Record<string, string> = { agent: 'Kit', owner: 'sahip' };
const OUTCOME_LABELS: Record<string, string> = {
  pending: 'bekliyor',
  succeeded: 'başarılı',
  failed: 'başarısız',
};
const ACTION_LABELS: Record<string, string> = {
  navigate: 'siteye git',
  snapshot: 'anlık görüntü',
  read: 'sayfayı oku',
  screenshot: 'ekran görüntüsü',
  watch: 'canlı izleme',
  click: 'tıkla',
  type: 'yaz',
  key: 'tuşa bas',
  scroll: 'kaydır',
  files_write: 'dosya yaz',
  files_read: 'dosya oku',
  files_list: 'dosyaları listele',
  exec: 'komut çalıştır',
  human_click: 'elle tıklama',
  human_type: 'elle yazma',
  human_key: 'elle tuş',
  human_scroll: 'elle kaydırma',
};

export function ComputerPanel({ dot }: { dot: Dot }) {
  const [tab, setTab] = useState<'Browser' | 'Files' | 'Terminal' | 'Activity'>(
    'Browser',
  );
  const [status, setStatus] = useState<ComputerStatus>();
  const [screen, setScreen] = useState<Screen>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState('');
  const [text, setText] = useState('');
  const [key, setKey] = useState('Enter');
  const [point, setPoint] = useState({ x: 0, y: 0 });
  const [path, setPath] = useState('');
  const [contents, setContents] = useState('');
  const [command, setCommand] = useState('');
  const [output, setOutput] = useState('');
  const [screenError, setScreenError] = useState('');
  const lifecycle = useRef({
    active: false,
    revision: 0,
    busy: false,
    loaded: false,
    running: false,
  });
  const controller = useRef<AbortController | null>(null);
  // Canlı izleme ve kayıt (P-044): aynı kare kaynağı; kayıt açıkken canlı izleme de açıktır.
  const [live, setLive] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordedFrames, setRecordedFrames] = useState(0);
  const [gif, setGif] = useState<{ url: string; name: string } | null>(null);
  const [gifBusy, setGifBusy] = useState(false);
  const liveRef = useRef(false);
  const recorder = useRef<FrameRecorder | null>(null);
  liveRef.current = live || recording;
  const base = `/dots/${encodeURIComponent(dot.id)}/computer`;
  const refresh = useCallback(async () => {
    const revision = lifecycle.current.revision;
    const current = () =>
      lifecycle.current.active && revision === lifecycle.current.revision;
    try {
      const next = await api<ComputerStatus>(
        base,
        'GET',
        undefined,
        controller.current?.signal,
      );
      if (!current()) return;
      setStatus(next);
      lifecycle.current.loaded = true;
      lifecycle.current.running = next.state === 'running';
      setError('');
      if (
        next.state === 'running' &&
        next.permissions.browser &&
        next.permissions.enabled
      ) {
        try {
          // İzleme karesi denetim kaydına yazılmaz (P-044); Kit'in kendi ekran
          // görüntüleri `actions` yolundan kaydedilmeye devam eder.
          const capture = await api<Screen>(
            `${base}/frame`,
            'GET',
            undefined,
            controller.current?.signal,
          );
          if (current()) {
            setScreen(capture);
            setScreenError('');
            const active = recorder.current;
            if (active && active.add(capture)) {
              setRecordedFrames(active.count);
              if (active.full) setRecording(false);
            }
          }
        } catch (cause) {
          if (current()) {
            setScreen(undefined);
            setScreenError(
              cause instanceof Error ? cause.message : 'Ekran yenilenemedi.',
            );
          }
        }
      } else {
        setScreen(undefined);
        setScreenError('');
      }
    } catch (cause) {
      if (current()) {
        setError(
          cause instanceof Error ? cause.message : 'Bilgisayar yüklenemedi.',
        );
        setScreen(undefined);
      }
    }
  }, [base]);
  useEffect(() => {
    lifecycle.current.active = true;
    controller.current = new AbortController();
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      if (
        !document.hidden &&
        !lifecycle.current.busy &&
        (!lifecycle.current.loaded || lifecycle.current.running)
      )
        await refresh();
      if (!cancelled && lifecycle.current.active)
        timer = setTimeout(() => void poll(), pollDelay(liveRef.current));
    };
    void poll();
    return () => {
      cancelled = true;
      lifecycle.current.active = false;
      lifecycle.current.revision++;
      controller.current?.abort();
      clearTimeout(timer);
    };
  }, [refresh]);
  const run = async (
    endpoint: string,
    body: unknown = {},
    method = 'POST',
    showOutput = false,
  ) => {
    if (lifecycle.current.busy) return;
    lifecycle.current.busy = true;
    lifecycle.current.revision++;
    setBusy(true);
    setError('');
    try {
      const result = await api<unknown>(
        `${base}${endpoint}`,
        method,
        body,
        controller.current?.signal,
      );
      if (!lifecycle.current.active) return;
      if (showOutput)
        setOutput(
          typeof result === 'string' ? result : JSON.stringify(result, null, 2),
        );
      await refresh();
      return result;
    } catch (cause) {
      if (lifecycle.current.active)
        setError(
          cause instanceof Error
            ? cause.message
            : 'Bilgisayar işlemi başarısız oldu.',
        );
    } finally {
      lifecycle.current.busy = false;
      if (lifecycle.current.active) setBusy(false);
    }
  };
  const startRecording = () => {
    setGif((previous) => {
      if (previous) URL.revokeObjectURL(previous.url);
      return null;
    });
    recorder.current = new FrameRecorder();
    setRecordedFrames(0);
    setRecording(true);
  };
  useEffect(() => {
    // Kayıt durunca (elle ya da kare tavanında) biriken kareler GIF'e çevrilir.
    if (recording || !recorder.current) return;
    const frames = recorder.current.take();
    recorder.current = null;
    if (frames.length === 0) return;
    setGifBusy(true);
    framesToGif(frames)
      .then((blob) => {
        const stamp = new Date(frames[0].capturedAt)
          .toISOString()
          .replace(/[:.]/g, '-');
        setGif({
          url: URL.createObjectURL(blob),
          name: `${dot.name}-kayit-${stamp}.gif`,
        });
      })
      .catch((cause) =>
        setScreenError(
          cause instanceof Error ? cause.message : 'GIF oluşturulamadı.',
        ),
      )
      .finally(() => setGifBusy(false));
  }, [recording, dot.name]);
  useEffect(
    () => () => {
      if (gif) URL.revokeObjectURL(gif.url);
    },
    [gif],
  );
  const action = (action: ComputerAction, input: unknown, showOutput = false) =>
    run('/actions', { action, input }, 'POST', showOutput);
  const running = status?.state === 'running' && status.permissions.enabled;
  const human =
    status?.control?.holder === 'human' && !status.control.transitioning;
  const browser = !!running && !!status?.permissions.browser;
  return (
    <section
      className="computer-panel"
      aria-label={`${dot.name} bilgisayarı`}
      aria-busy={busy}
    >
      {error && (
        <p className="computer-error" role="alert">
          {error}
        </p>
      )}
      {!status ? (
        <p role="status">
          {error ? 'Bilgisayar durumu alınamadı.' : 'Bilgisayar yükleniyor…'}
        </p>
      ) : (
        <>
          <div className="computer-status">
            <strong>{STATE_LABELS[status.state] ?? status.state}</strong>
            {status.local && <small>Yerel bilgisayar (Docker'sız)</small>}
            {status.state !== 'running' && (
              <button disabled={busy} onClick={() => void refresh()}>
                Yenile
              </button>
            )}
            <span>
              {busy ? 'Çalışıyor…' : human ? 'Kontrol sende' : 'Kontrol Kit’te'}
            </span>
          </div>
          {!status.configured && (
            <div className="computer-setup">
              <h3>Bilgisayar hizmetini bağla</h3>
              <p>
                Bu Kit için bir bilgisayar hizmeti yapılandırılmamış. Yerel
                bilgisayar KITS_LOCAL_COMPUTER=0 ile kapatılmış olabilir; açmak
                için bu ayarı kaldır ya da bilgisayar hizmeti adresini ve
                anahtarını ayarla, ardından yeniden başlat. Her Kit kendi
                tarayıcısına ve çalışma alanına sahip olur.
              </p>
              <p>
                Fusion ana uygulamasında bilgisayar erişimini açıp yeniden dene.
              </p>
            </div>
          )}
          {status.error && (
            <p className="computer-error" role="alert">
              {status.error}
            </p>
          )}
          <div
            className="computer-tool-tabs"
            role="tablist"
            aria-label="Bilgisayar araçları"
          >
            {(['Browser', 'Files', 'Terminal', 'Activity'] as const).map(
              (name) => (
                <button
                  role="tab"
                  aria-selected={tab === name}
                  key={name}
                  onClick={() => setTab(name)}
                >
                  {TAB_LABELS[name]}
                </button>
              ),
            )}
          </div>
          {status.configured && (
            <>
              <section
                className="computer-section computer-browser"
                hidden={tab !== 'Browser'}
              >
                {!status.permissions.browser && (
                  <p>Ekranı kullanmak için Tarayıcı iznini aç.</p>
                )}
                <form
                  className="computer-row"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void action('navigate', { url });
                  }}
                >
                  <input
                    type="url"
                    aria-label="Tarayıcı adresi"
                    placeholder="https://example.com"
                    value={url}
                    onChange={(event) => setUrl(event.target.value)}
                    required
                    disabled={!browser || busy || human}
                  />
                  <button disabled={!browser || busy || human || !url.trim()}>
                    Git
                  </button>
                </form>
                {screenError && (
                  <p className="computer-error" role="status">
                    {screenError}
                  </p>
                )}
                {screen ? (
                  <>
                    <div className="computer-current-url" title={screen.url}>
                      {screen.url || 'Tarayıcı ekranı'}
                    </div>
                    <button
                      className="computer-screen"
                      aria-label={
                        human
                          ? 'Bilgisayar ekranında bir noktaya tıkla'
                          : 'Bilgisayar ekranı; etkileşim için kontrolü devral'
                      }
                      disabled={!browser || !human || busy}
                      onClick={(event) => {
                        const rect =
                          event.currentTarget.getBoundingClientRect();
                        void action('human_click', {
                          x: Math.min(
                            screen.width - 1,
                            Math.max(
                              0,
                              Math.floor(
                                ((event.clientX - rect.left) / rect.width) *
                                  screen.width,
                              ),
                            ),
                          ),
                          y: Math.min(
                            screen.height - 1,
                            Math.max(
                              0,
                              Math.floor(
                                ((event.clientY - rect.top) / rect.height) *
                                  screen.height,
                              ),
                            ),
                          ),
                        });
                      }}
                    >
                      <img
                        src={`data:image/png;base64,${screen.base64}`}
                        alt={`${dot.name} için canlı tarayıcı ekranı`}
                      />
                    </button>
                    <small>
                      Yenilendi:{' '}
                      {new Date(screen.capturedAt).toLocaleTimeString()}.{' '}
                      {live || recording
                        ? 'Canlı izleniyor (saniyede bir kare).'
                        : 'Bu panel açıkken ekran güncellenir.'}
                    </small>
                    <div className="computer-recording" aria-live="polite">
                      <button
                        type="button"
                        aria-pressed={live || recording}
                        disabled={recording}
                        onClick={() => setLive((value) => !value)}
                      >
                        {live ? 'Canlı izlemeyi durdur' : 'Canlı izle'}
                      </button>
                      <button
                        type="button"
                        aria-pressed={recording}
                        disabled={gifBusy}
                        onClick={() =>
                          recording ? setRecording(false) : startRecording()
                        }
                      >
                        {recording
                          ? `Kaydı durdur (${recordedFrames}/${MAX_RECORDING_FRAMES} kare)`
                          : 'GIF kaydı başlat'}
                      </button>
                      {gifBusy && <span>GIF hazırlanıyor…</span>}
                      {gif && (
                        <a href={gif.url} download={gif.name}>
                          GIF'i indir
                        </a>
                      )}
                    </div>
                  </>
                ) : (
                  <p className="computer-screen-empty">
                    {running && status.permissions.browser
                      ? 'Tarayıcı ekranı bekleniyor…'
                      : 'Ekranı görmek için bilgisayarı Tarayıcı iznini vererek başlat.'}
                  </p>
                )}
                <div className="computer-control-pill">
                  <span>
                    {human ? 'Kontrol sende' : `Kontrol ${dot.name} Kit’inde`}
                  </span>
                  <button
                    disabled={
                      (!human && !browser) ||
                      busy ||
                      status.control?.transitioning
                    }
                    onClick={() => void run(human ? '/release' : '/take')}
                  >
                    {human ? 'Kontrolü geri ver' : 'Kontrolü devral'}
                  </button>
                </div>
                {status.control?.transitioning && (
                  <p role="status">Kontrol aktarılıyor…</p>
                )}
                {human && (
                  <details className="computer-human">
                    <summary>Klavye ve hassas kontroller</summary>
                    <p>
                      Ekrana tıkla veya aşağıya koordinat gir. Metin sohbete
                      girmeden doğrudan bu tarayıcıya gider. İşin bitince
                      kontrolü geri ver.
                    </p>
                    <form
                      className="computer-row"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void action('human_click', point);
                      }}
                    >
                      <label>
                        X
                        <input
                          type="number"
                          min="0"
                          max={screen ? screen.width - 1 : undefined}
                          value={point.x}
                          onChange={(event) =>
                            setPoint({
                              ...point,
                              x: Number(event.target.value),
                            })
                          }
                        />
                      </label>
                      <label>
                        Y
                        <input
                          type="number"
                          min="0"
                          max={screen ? screen.height - 1 : undefined}
                          value={point.y}
                          onChange={(event) =>
                            setPoint({
                              ...point,
                              y: Number(event.target.value),
                            })
                          }
                        />
                      </label>
                      <button disabled={busy || !browser || !screen}>
                        Tıkla
                      </button>
                    </form>
                    <form
                      className="computer-row"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const value = text;
                        setText('');
                        void action('human_type', { text: value });
                      }}
                    >
                      <input
                        type="password"
                        aria-label="Bilgisayara yazılacak metin"
                        placeholder="Odaklı alana yaz"
                        autoComplete="off"
                        value={text}
                        maxLength={20000}
                        onChange={(event) => setText(event.target.value)}
                      />
                      <button disabled={busy || !browser || !text}>Yaz</button>
                    </form>
                    <form
                      className="computer-row"
                      onSubmit={(event) => {
                        event.preventDefault();
                        void action('human_key', { key });
                      }}
                    >
                      <select
                        aria-label="Basılacak tuş"
                        value={key}
                        onChange={(event) => setKey(event.target.value)}
                      >
                        {[
                          'Enter',
                          'Tab',
                          'Escape',
                          'Backspace',
                          'ArrowUp',
                          'ArrowDown',
                          'ArrowLeft',
                          'ArrowRight',
                        ].map((name) => (
                          <option key={name}>{name}</option>
                        ))}
                      </select>
                      <button disabled={busy || !browser}>Tuşa bas</button>
                    </form>
                    <div className="computer-actions">
                      <button
                        disabled={busy || !browser}
                        onClick={() =>
                          void action('human_scroll', { deltaY: -500 })
                        }
                      >
                        Yukarı kaydır
                      </button>
                      <button
                        disabled={busy || !browser}
                        onClick={() =>
                          void action('human_scroll', { deltaY: 500 })
                        }
                      >
                        Aşağı kaydır
                      </button>
                    </div>
                  </details>
                )}
              </section>
              <details
                className="computer-section"
                open
                hidden={tab !== 'Files'}
              >
                <summary>Çalışma alanı dosyaları</summary>
                <p>Yollar bu Kit’in kalıcı çalışma alanına görelidir.</p>
                <label>
                  Yol
                  <input
                    value={path}
                    onChange={(event) => setPath(event.target.value)}
                    placeholder="notes.txt"
                    disabled={!running || !status.permissions.files || busy}
                  />
                </label>
                <div className="computer-actions">
                  <button
                    disabled={!running || !status.permissions.files || busy}
                    onClick={() => void action('files_list', { path }, true)}
                  >
                    Dosyaları listele
                  </button>
                  <button
                    disabled={
                      !running ||
                      !status.permissions.files ||
                      busy ||
                      !path.trim()
                    }
                    onClick={() =>
                      void action('files_read', { path }, true).then(
                        (result) => {
                          if (
                            lifecycle.current.active &&
                            result &&
                            typeof result === 'object' &&
                            'text' in result &&
                            typeof result.text === 'string'
                          )
                            setContents(result.text);
                        },
                      )
                    }
                  >
                    Dosyayı oku
                  </button>
                </div>
                <label>
                  Dosya içeriği
                  <textarea
                    aria-label="Kaydedilecek dosya içeriği"
                    value={contents}
                    onChange={(event) => setContents(event.target.value)}
                    disabled={!running || !status.permissions.files || busy}
                    maxLength={100000}
                    rows={5}
                  />
                </label>
                <button
                  disabled={
                    !running ||
                    !status.permissions.files ||
                    busy ||
                    !path.trim()
                  }
                  onClick={() =>
                    void action('files_write', { path, contents }, true)
                  }
                >
                  Dosyayı kaydet (içeriği değiştir)
                </button>
                {!status.permissions.files && (
                  <p>
                    Bu kontrolleri kullanmak için Çalışma alanı dosyaları iznini
                    aç.
                  </p>
                )}
              </details>
              <details
                className="computer-section"
                open
                hidden={tab !== 'Terminal'}
              >
                <summary>Terminal</summary>
                <p>
                  Bu Kit’in bilgisayarında çalışır. Komutlar 30 saniye sonra
                  durdurulur.
                </p>
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    void action('exec', { command, timeoutMs: 30000 }, true);
                  }}
                >
                  <textarea
                    aria-label="Terminal komutu"
                    value={command}
                    onChange={(event) => setCommand(event.target.value)}
                    maxLength={8000}
                    rows={3}
                    disabled={!running || !status.permissions.shell || busy}
                    placeholder="pwd"
                  />
                  <button
                    disabled={
                      !running ||
                      !status.permissions.shell ||
                      busy ||
                      !command.trim()
                    }
                  >
                    Komutu çalıştır
                  </button>
                </form>
                {!status.permissions.shell && (
                  <p>Komut çalıştırmak için Terminal komutları iznini aç.</p>
                )}
              </details>
              {output && (tab === 'Files' || tab === 'Terminal') && (
                <section className="computer-section">
                  <h3>Çıktı</h3>
                  <pre tabIndex={0}>{output}</pre>
                  <button onClick={() => setOutput('')}>Çıktıyı temizle</button>
                </section>
              )}
            </>
          )}
          <details
            className="computer-section"
            open
            hidden={tab !== 'Activity'}
          >
            <summary>Son etkinlik</summary>
            {status.audit.length ? (
              <ol className="computer-audit">
                {status.audit
                  .slice(-30)
                  .reverse()
                  .map((entry) => (
                    <li key={entry.id}>
                      <strong>
                        {ACTION_LABELS[entry.action] ??
                          entry.action.replaceAll('_', ' ')}
                      </strong>
                      <span>
                        {ACTOR_LABELS[entry.actor] ?? entry.actor} ·{' '}
                        {OUTCOME_LABELS[entry.outcome] ?? entry.outcome} ·{' '}
                        {new Date(entry.createdAt).toLocaleTimeString()}
                      </span>
                    </li>
                  ))}
              </ol>
            ) : (
              <p>Henüz bilgisayar işlemi yok.</p>
            )}
          </details>
          <details className="computer-settings">
            <summary>Bilgisayar ayarları</summary>{' '}
            <details
              className="computer-permissions"
              open={!status.permissions.enabled}
            >
              <summary>Bilgisayar izinleri</summary>
              <p>
                {dot.name} Kit’inin ve bilgisayar kontrollerinin nelere
                erişebileceğini seç.
              </p>
              {(['enabled', 'browser', 'files', 'shell'] as const).map(
                (permission) => (
                  <label key={permission}>
                    <input
                      type="checkbox"
                      checked={status.permissions[permission]}
                      disabled={busy || !status.configured}
                      onChange={(event) =>
                        void run(
                          '/permissions',
                          { [permission]: event.target.checked },
                          'PATCH',
                        )
                      }
                    />
                    {
                      {
                        enabled: 'Bu bilgisayarı etkinleştir',
                        browser: 'Tarayıcı',
                        files: 'Çalışma alanı dosyaları',
                        shell: 'Terminal komutları',
                      }[permission]
                    }
                  </label>
                ),
              )}
            </details>
            <div className="computer-actions">
              <button
                disabled={
                  busy ||
                  !status.configured ||
                  !status.permissions.enabled ||
                  status.state === 'running'
                }
                onClick={() => void run('/start')}
              >
                Bilgisayarı başlat
              </button>
              <button
                disabled={busy || status.state !== 'running'}
                onClick={() => void run('/stop')}
              >
                Bilgisayarı durdur
              </button>
            </div>
            <p className="computer-hint">
              Durdurmak bu Kit’in çalışma alanı dosyalarını korur. Tarayıcı
              oturumları için yeniden giriş yapmak gerekebilir.
            </p>
          </details>
        </>
      )}
    </section>
  );
}

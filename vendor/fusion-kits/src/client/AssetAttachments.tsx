import { useEffect, useMemo, useRef, useState } from 'react';
import { assetIds, assetLink } from './asset-markdown';
import {
  requestAssetPage,
  requestAssetPreview,
  requestAssetReference,
  type AssetApi,
  type AssetCursor,
  type AssetReference,
  type AssetView,
} from './asset-bridge';
import './asset-attachments.css';

const defaultApi: AssetApi = async <T,>(
  path: string,
  method?: string,
  body?: unknown,
  signal?: AbortSignal,
) => {
  const { api } = await import('./api');
  return api<T>(path, method, body, signal);
};

export function AssetFileCard({
  id,
  view = globalThis.window,
  apiClient = defaultApi,
}: {
  id: string;
  view?: AssetView;
  apiClient?: AssetApi;
}) {
  const [asset, setAsset] = useState<AssetReference | null>(null);
  const [preview, setPreview] = useState('');
  const [message, setMessage] = useState('Dosya doğrulanıyor…');
  const element = useRef<HTMLElement | null>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        setVisible(true);
        observer.disconnect();
      }
    });
    if (element.current) observer.observe(element.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!visible || !view) return;
    const owned = new AbortController();
    setAsset(null);
    setPreview('');
    setMessage('Dosya doğrulanıyor…');
    void (async () => {
      const result = await requestAssetReference(view, apiClient, id, {
        signal: owned.signal,
      });
      if (owned.signal.aborted) return;
      if (result.status === 'unavailable') {
        setMessage(result.message);
        return;
      }
      setAsset(result.asset);
      if (result.status === 'missing') {
        setMessage('Dosya artık bulunamıyor; belge kimliği korundu.');
        return;
      }
      setMessage('');
      if (result.asset.kind !== 'image') return;
      const image = await requestAssetPreview(view, apiClient, id, {
        signal: owned.signal,
      });
      if (owned.signal.aborted) return;
      if (image.status === 'ready') setPreview(image.value.data_url);
      else setMessage('Bu dosyanın önizlemesi kullanılamıyor.');
    })().catch(() => {
      if (!owned.signal.aborted) setMessage('Dosya doğrulanamadı.');
    });
    return () => owned.abort();
  }, [id, view, apiClient, visible]);
  return (
    <figure
      ref={element}
      tabIndex={-1}
      className="asset-file-card"
      data-asset-id={id}
    >
      {preview && (
        <img
          src={preview}
          alt={asset?.relative_path.split('/').at(-1) || 'Ek görsel'}
          width={240}
          height={180}
          onError={() => {
            setPreview('');
            setMessage('Görsel açılamadı.');
          }}
        />
      )}
      <figcaption>
        {asset?.relative_path.split('/').at(-1) || 'Fusion dosyası'}
      </figcaption>
      {message && <p role="status">{message}</p>}
    </figure>
  );
}

interface Props {
  scope: string;
  content: string;
  onInsert: (markdown: string) => void;
  view?: AssetView;
  apiClient?: AssetApi;
}
export function AssetAttachments(props: Props) {
  return <Attachments key={props.scope} {...props} />;
}
function Attachments({
  content,
  onInsert,
  view = globalThis.window,
  apiClient = defaultApi,
}: Props) {
  const ids = useMemo(() => assetIds(content), [content]);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<AssetReference[]>([]);
  const [cursor, setCursor] = useState<AssetCursor>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef<AbortController | null>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  const enabled = Boolean(
    view &&
    view.parent !== view.self &&
    typeof globalThis.location === 'object' &&
    new URLSearchParams(globalThis.location.search).get('asset_protocol') ===
      '1',
  );
  useEffect(() => () => pending.current?.abort(), []);
  const load = async (next: AssetCursor) => {
    if (pending.current) return;
    const operation = new AbortController();
    pending.current = operation;
    setBusy(true);
    setError('');
    try {
      const result = await requestAssetPage(view, apiClient, next, {
        signal: operation.signal,
      });
      if (operation.signal.aborted || pending.current !== operation) return;
      if (result.status === 'unavailable') {
        setError(result.message);
        return;
      }
      setItems((old) =>
        next === null
          ? result.value.items
          : [
              ...old,
              ...result.value.items.filter(
                (item) =>
                  !old.some((existing) => existing.asset_id === item.asset_id),
              ),
            ],
      );
      setCursor(result.value.next_cursor);
    } finally {
      if (pending.current === operation) {
        pending.current = null;
        setBusy(false);
      }
    }
  };
  return (
    <section className="asset-attachments" aria-label="Fusion ek dosyaları">
      {enabled && (
        <button
          ref={opener}
          type="button"
          aria-expanded={open}
          onClick={() => {
            if (open) {
              pending.current?.abort();
              pending.current = null;
              setBusy(false);
              setOpen(false);
            } else {
              setOpen(true);
              setItems([]);
              setCursor(null);
              void load(null);
            }
          }}
        >
          Fusion'dan görsel ekle
        </button>
      )}
      {open && (
        <div className="asset-picker">
          <p>Galerideki görsel aynı dosya kimliğiyle eklenir.</p>
          {error && (
            <p role="alert">
              {error}{' '}
              <button type="button" onClick={() => void load(cursor)}>
                Yeniden dene
              </button>
            </p>
          )}
          <div className="asset-picker-items">
            {items.map((item) => (
              <button
                key={item.asset_id}
                type="button"
                disabled={!item.available || ids.includes(item.asset_id)}
                onClick={() => {
                  onInsert(
                    assetLink(
                      item.asset_id,
                      item.relative_path.split('/').at(-1) || 'Görsel',
                    ),
                  );
                  opener.current?.focus();
                  setOpen(false);
                }}
              >
                {item.relative_path.split('/').at(-1)}
                {!item.available
                  ? ' · bulunamadı'
                  : ids.includes(item.asset_id)
                    ? ' · eklendi'
                    : ''}
              </button>
            ))}
          </div>
          {busy && <p role="status">Dosyalar yükleniyor…</p>}
          {!busy && !error && items.length === 0 && <p>Galeride görsel yok.</p>}
          {cursor && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void load(cursor)}
            >
              Daha fazla görsel
            </button>
          )}
          <p>Maske ile bölgesel düzenleme bu köprüde desteklenmiyor.</p>
        </div>
      )}
      {ids.length > 0 && (
        <div className="asset-attachment-cards">
          {ids.slice(0, 8).map((id) => (
            <AssetFileCard key={id} id={id} view={view} apiClient={apiClient} />
          ))}
        </div>
      )}
      {ids.length > 8 && (
        <p>
          İlk 8 ekin önizlemesi gösteriliyor; tüm kimlikler belgede korunur.
        </p>
      )}
    </section>
  );
}

import { useEffect, useState } from 'react';
import { Cpu, X } from 'lucide-react';
import type { FusionSnapshot } from '../shared/fusion';
import { api } from './api';
import { FusionCard } from './FusionCard';

export function FusionPanel({
  threadId,
  onClose,
  embedded = false,
}: {
  threadId?: string;
  onClose?: () => void;
  embedded?: boolean;
}) {
  const [state, setState] = useState<FusionSnapshot>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setState(undefined);
    setError('');
    if (!threadId) return;
    let active = true;
    const controller = new AbortController();
    const load = async () => {
      try {
        const next = await api<FusionSnapshot>(
          `/conversations/${encodeURIComponent(threadId)}/fusion`,
          'GET',
          undefined,
          controller.signal,
        );
        if (active) {
          setState(next);
          setError('');
        }
      } catch (error) {
        if (active)
          setError(
            error instanceof Error
              ? error.message
              : 'Fusion durumu yüklenemedi.',
          );
      }
    };
    void load();
    const timer = setInterval(() => void load(), 1000);
    return () => {
      active = false;
      clearInterval(timer);
      controller.abort();
    };
  }, [threadId]);
  const mutate = async (action: string, body: unknown) => {
    if (!threadId) return;
    setBusy(true);
    setError('');
    try {
      await api(
        `/conversations/${encodeURIComponent(threadId)}/fusion/${action}`,
        'POST',
        body,
      );
      const next = await api<FusionSnapshot>(
        `/conversations/${encodeURIComponent(threadId)}/fusion`,
      );
      setState(next);
    } catch (error) {
      setError(
        error instanceof Error ? error.message : 'Fusion işlemi başarısız.',
      );
    } finally {
      setBusy(false);
    }
  };
  if (embedded && !error && (!state || state.status === 'idle')) return null;
  return (
    <aside
      className={embedded ? 'fusion-panel-inline' : 'fusion-panel'}
      aria-label="Fusion çekirdeği"
    >
      <header>
        <strong>
          <Cpu size={17} /> Fusion çekirdeği
        </strong>
        {onClose && (
          <button
            className="icon-button"
            aria-label="Fusion panelini kapat"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        )}
      </header>
      {error && (
        <p role="alert" className="chat-error">
          {error}
        </p>
      )}
      {!threadId ? (
        <p className="muted">
          Bir sohbet seçin. Kit’in Fusion görevleri ve bekleyen kararları burada
          görünür.
        </p>
      ) : state ? (
        <FusionCard
          state={state}
          busy={busy}
          onReply={(answer) =>
            void mutate('reply', {
              runId: state.runId,
              questionId: state.question?.id,
              answer,
            })
          }
          onCancel={() => void mutate('cancel', { runId: state.runId })}
        />
      ) : (
        <p className="muted">Çekirdek durumu yükleniyor…</p>
      )}
    </aside>
  );
}

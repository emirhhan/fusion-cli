import { useThreads } from '@copilotkit/react-core/v2';
import { MessageCircle, Plus } from 'lucide-react';
import type { Conversation, Dot } from '../shared/types';
import { mergeThreadRows } from './thread-list';
export function ThreadList({
  dots,
  dotId,
  local,
  selected,
  onSelect,
  onNew,
}: {
  dots: Dot[];
  dotId: string;
  local: Conversation[];
  selected?: string;
  onSelect: (id: string, dotId: string) => void;
  onNew: () => void;
}) {
  const threads = useThreads({
    agentId: dotId,
    enabled: true,
    includeArchived: false,
    limit: 20,
  });
  const rows = mergeThreadRows(local, threads.threads, dotId);
  return (
    <section className="thread-list">
      <div className="nav-label">
        Sohbetler
        <button
          className="icon-button"
          onClick={onNew}
          aria-label="Yeni sohbet"
        >
          <Plus size={14} />
        </button>
      </div>
      {threads.error && (
        <p className="sidebar-error">
          Sohbet eşitlemesi kullanılamıyor. Çalışma ortamı bağlantını kontrol
          et.
        </p>
      )}
      {rows.map((thread) => {
        return (
          <button
            key={thread.id}
            className={`nav-item ${selected === thread.id ? 'active' : ''}`}
            onClick={() => onSelect(thread.id, thread.dotId)}
          >
            <MessageCircle size={15} />
            <span className="thread-summary">
              <span>{thread.title}</span>
              <small>{dots.find((dot) => dot.id === thread.dotId)?.name}</small>
            </span>
          </button>
        );
      })}
      {!rows.length && (
        <p className="sidebar-empty">İlk sohbetiniz burada görünecek.</p>
      )}
      {threads.hasMoreThreads && (
        <button
          className="text-button"
          disabled={threads.isFetchingMoreThreads}
          onClick={() => void threads.fetchMoreThreads()}
        >
          Daha fazla sohbet
        </button>
      )}
    </section>
  );
}

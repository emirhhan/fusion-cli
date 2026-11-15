import { useEffect, useRef, useState } from 'react';
import { Check, FileText, ArrowUpRight } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { pageReviewSchema } from '../shared/page-review';
import { decidePageReview, restorePageReview } from './page-review-decision';
import { computerToolResult } from './ComputerToolCard';
import { openPageLink } from './page-navigation';
import type { Page } from '../server/pages';
export function PageReviewCard({
  args,
  status,
  result,
  respond,
  threadId,
  toolCallId,
  onSaved,
}: {
  args: unknown;
  status: string;
  result?: unknown;
  respond?: (result: unknown) => Promise<void>;
  threadId: string;
  toolCallId: string;
  onSaved: () => void;
}) {
  const draft = pageReviewSchema.safeParse(args);
  const outcome = computerToolResult(result);
  const [savedPage, setSavedPage] = useState<Page>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [receiptReady, setReceiptReady] = useState(false);
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const pending = useRef(false);
  const finished = status === 'complete';
  const recordedApproval = outcome.approved === true;
  const saved = !!savedPage || recordedApproval;
  const pageId =
    savedPage?.id ?? (typeof outcome.pageId === 'string' ? outcome.pageId : '');
  const spaceId =
    savedPage?.spaceId ??
    (typeof outcome.spaceId === 'string' ? outcome.spaceId : '');
  useEffect(() => {
    if (recordedApproval) return;
    let active = true;
    setReceiptReady(false);
    setError('');
    void restorePageReview(threadId, toolCallId)
      .then((page) => {
        if (!active) return;
        setSavedPage(page ?? undefined);
        setReceiptReady(true);
      })
      .catch((cause) => {
        if (active)
          setError(
            cause instanceof Error
              ? cause.message
              : 'Bu inceleme geri yüklenemedi.',
          );
      });
    return () => {
      active = false;
    };
  }, [threadId, toolCallId, recordedApproval, restoreAttempt]);
  const decide = async (approved: boolean) => {
    if (!respond || !receiptReady || pending.current) return;
    pending.current = true;
    setBusy(true);
    setError('');
    try {
      const page = await decidePageReview(threadId, toolCallId, args, approved);
      if (!page) {
        await respond({
          approved: false,
          message: 'The owner declined this draft. Do not save it.',
        });
        return;
      }
      setSavedPage(page);
      onSaved();
      await respond({
        approved: true,
        pageId: page.id,
        spaceId: page.spaceId,
        url: `/#/spaces/${page.spaceId}/pages/${page.id}`,
      });
    } catch (cause) {
      setReceiptReady(false);
      setError(
        cause instanceof Error
          ? cause.message
          : 'Onaylanan taslak kaydedilemedi.',
      );
    } finally {
      pending.current = false;
      setBusy(false);
    }
  };
  return (
    <section className="page-review-card" aria-label="Sayfa taslağını incele">
      <header>
        <FileText size={17} />
        <strong>
          {saved
            ? 'Alanına kaydedildi'
            : !receiptReady
              ? 'Kayıtlı inceleme denetleniyor…'
              : finished
                ? 'İnceleme sona erdi'
                : 'İncelemene hazır'}
        </strong>
        <span>
          {saved
            ? 'Onaylandı'
            : !receiptReady
              ? 'Denetleniyor'
              : finished
                ? 'Kaydedilmedi'
                : 'Karar senin'}
        </span>
      </header>
      <div className="page-review-body">
        <h3>{draft.success ? draft.data.title : 'Taslağın hazırlanıyor…'}</h3>
        {draft.success && (
          <ReactMarkdown
            components={{
              img: ({ alt }) => <span>{alt}</span>,
              a: ({ href, children }) => (
                <a href={href} target="_blank" rel="noreferrer">
                  {children}
                </a>
              ),
            }}
          >
            {draft.data.content}
          </ReactMarkdown>
        )}
      </div>
      {error && <p role="alert">{error}</p>}
      {!receiptReady && error && (
        <button
          type="button"
          onClick={() => setRestoreAttempt((attempt) => attempt + 1)}
        >
          İncelemeyi yeniden dene
        </button>
      )}
      <footer>
        {saved && pageId && spaceId && (
          <button
            type="button"
            className="review-primary"
            onClick={() =>
              openPageLink(
                `/#/spaces/${encodeURIComponent(spaceId)}/pages/${encodeURIComponent(pageId)}`,
              )
            }
          >
            Sayfayı aç <ArrowUpRight size={15} />
          </button>
        )}
        {!finished && respond && receiptReady && (
          <>
            <button
              type="button"
              disabled={busy || (!saved && !draft.success)}
              className="review-primary"
              onClick={() => void decide(true)}
            >
              <Check size={15} />
              {busy
                ? 'Kaydediliyor…'
                : saved
                  ? 'Sohbete devam et'
                  : 'Onayla ve kaydet'}
            </button>
            {!saved && (
              <button
                type="button"
                disabled={busy}
                onClick={() => void decide(false)}
              >
                Reddet
              </button>
            )}
          </>
        )}
        {!saved && (
          <small>
            {!receiptReady
              ? 'Bu taslağın daha önce kaydedilip kaydedilmediği denetleniyor.'
              : finished
                ? 'Hiçbir sayfa kaydedilmedi.'
                : 'Sen onaylamadan hiçbir şey kaydedilmez.'}
          </small>
        )}
      </footer>
    </section>
  );
}

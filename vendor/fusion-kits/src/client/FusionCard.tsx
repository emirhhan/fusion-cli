import { useEffect, useState } from 'react';
import { Square } from 'lucide-react';
import type { FusionSnapshot } from '../shared/fusion';

const labels: Record<FusionSnapshot['status'], string> = {
  idle: 'Hazır',
  running: 'Çalışıyor',
  waiting: 'Cevabınızı bekliyor',
  completed: 'Tamamlandı',
  failed: 'Başarısız',
  cancelled: 'İptal edildi',
};
const text = (value: unknown) => (typeof value === 'string' ? value : '');
export function FusionCard({
  state,
  busy,
  onReply,
  onCancel,
}: {
  state: FusionSnapshot;
  busy: boolean;
  onReply: (answer: Record<string, unknown>) => void;
  onCancel: () => void;
}) {
  const [answer, setAnswer] = useState('');
  useEffect(() => setAnswer(''), [state.runId, state.question?.id]);
  if (!state.configured)
    return (
      <p className="muted">
        Fusion çekirdeği yapılandırılmadı. Kurulum rehberindeki FUSION_COMMAND,
        FUSION_ROOT ve FUSION_HOME alanlarını ayarlayın. Kits’in diğer araçları
        ayrı yapılandırmalarıyla çalışır.
      </p>
    );
  const question = state.question?.data;
  const options = Array.isArray(question?.secenekler)
    ? (question.secenekler.filter(
        (option) => option && typeof option === 'object',
      ) as Record<string, unknown>[])
    : [];
  return (
    <div className="fusion-card">
      <div className="fusion-card-status">
        <strong>{labels[state.status]}</strong>
        {['running', 'waiting'].includes(state.status) && (
          <button disabled={busy} onClick={onCancel}>
            <Square size={13} /> Görevi durdur
          </button>
        )}
      </div>
      <p className="fusion-root">
        Yerel proje: <code>{state.root}</code>
      </p>
      {state.modelReceipts?.map((receipt) => (
        <p key={receipt.callId}>
          İstenen: {receipt.requestedModel} · Gözlenen:{' '}
          {receipt.observedModel ?? 'doğrulanamadı'}
          {receipt.appliedModel !== receipt.requestedModel &&
            ` · Uygulanan yedek: ${receipt.appliedModel}`}
          {(receipt.requestedEffort || receipt.appliedEffort) &&
            ` · İstenen yoğunluk: ${receipt.requestedEffort ?? 'doğrulanamadı'} · Uygulanan yoğunluk: ${receipt.appliedEffort ?? 'gönderilmedi'}`}
          {receipt.effortReason && ` · ${receipt.effortReason}`}
        </p>
      ))}
      {state.text && <pre className="fusion-output">{state.text}</pre>}
      {state.error && (
        <p role="alert" className="chat-error">
          {state.error}
        </p>
      )}
      {question && (
        <section className="fusion-question" aria-label="Fusion kararı">
          <h3>
            {text(question.baslik) ||
              text(question.soru) ||
              'Fusion cevabınızı bekliyor'}
          </h3>
          {text(question.hedef) && <code>{text(question.hedef)}</code>}
          {text(question.tehlike) && (
            <p role="alert">{text(question.tehlike)}</p>
          )}
          {text(question.neden) && <p>{text(question.neden)}</p>}
          {question.argumanlar != null && (
            <details open>
              <summary>İşlem parametreleri</summary>
              <pre>
                {Array.isArray(question.argumanlar)
                  ? question.argumanlar
                      .map((value) =>
                        typeof value === 'string'
                          ? value
                          : JSON.stringify(value),
                      )
                      .join('\n')
                  : JSON.stringify(question.argumanlar, null, 2)}
              </pre>
            </details>
          )}
          {text(question.diff) && <pre>{text(question.diff)}</pre>}
          {question.tur === 'onay' ? (
            <div className="fusion-decisions">
              <button
                disabled={busy}
                onClick={() => onReply({ secim: 'deny' })}
              >
                Reddet
              </button>
              <button
                disabled={busy}
                className="primary"
                onClick={() => onReply({ secim: 'once' })}
              >
                Bir kez izin ver
              </button>
              {!question.tehlike && (
                <button
                  disabled={busy}
                  onClick={() => onReply({ secim: 'session' })}
                >
                  Bu oturumda izin ver
                </button>
              )}
            </div>
          ) : question.tur === 'soru' ? (
            <form
              onSubmit={(event) => {
                event.preventDefault();
                if (answer.trim()) onReply({ metin: answer.trim() });
              }}
            >
              {options.map((option, index) => (
                <button
                  type="button"
                  key={index}
                  disabled={busy}
                  onClick={() =>
                    setAnswer(text(option.deger) || text(option.etiket))
                  }
                >
                  {text(option.etiket)}
                  {text(option.aciklama) && ` — ${text(option.aciklama)}`}
                </button>
              ))}
              <label htmlFor={`fusion-answer-${state.runId}`}>Cevabınız</label>
              <textarea
                id={`fusion-answer-${state.runId}`}
                maxLength={4000}
                value={answer}
                disabled={busy}
                onChange={(event) => setAnswer(event.target.value)}
                required
              />
              <button disabled={busy || !answer.trim()} type="submit">
                Cevabı gönder
              </button>
            </form>
          ) : (
            <p role="alert">
              Bu soru türü desteklenmiyor. Görevi durdurabilirsiniz.
            </p>
          )}
        </section>
      )}
      {state.events.length > 0 && (
        <details>
          <summary>Çekirdek etkinliği</summary>
          <ol>
            {state.events.map((event, index) => (
              <li key={index}>{event}</li>
            ))}
          </ol>
        </details>
      )}
      {state.status === 'idle' && (
        <p className="muted">
          Kit ayarlarında Fusion görev iznini açın, ardından sohbetten bir proje
          görevi isteyin. Çekirdek yalnız görev çağrıldığında başlatılır.
        </p>
      )}
    </div>
  );
}

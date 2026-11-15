import { useState } from 'react';
import {
  ArrowDownToLine,
  ArrowUpRight,
  BookOpen,
  ExternalLink,
  Monitor,
  X,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import type { Dot, Result, Status } from '../shared/types';
import { Mascot } from './Mascot';
import { ComputerPanel } from './ComputerPanel';
export function ResultPane({
  latest,
  status,
  dotState,
  onClose,
  dots,
  defaultDotId,
}: {
  dots: Dot[];
  defaultDotId: string;
  latest?: Result | null;
  status?: Status;
  dotState: string;
  onClose: () => void;
}) {
  const [resultTab, setResultTab] = useState<'Brief' | 'Computer'>('Computer');
  const [computerDotId, setComputerDotId] = useState(defaultDotId);
  const computerDot =
    dots.find((dot) => dot.id === computerDotId) ??
    dots.find((dot) => dot.id === defaultDotId) ??
    dots[0];
  return (
    <aside className="result-pane">
      <div className="pane-header">
        <div className="pane-tabs">
          <button
            className={resultTab === 'Brief' ? 'selected' : ''}
            onClick={() => setResultTab('Brief')}
          >
            <BookOpen size={15} />
            Özet
          </button>
          <button
            className={resultTab === 'Computer' ? 'selected' : ''}
            onClick={() => setResultTab('Computer')}
          >
            <Monitor size={15} /> {computerDot?.name ?? 'Kit'} bilgisayarı
          </button>
        </div>
        <button
          className="icon-button"
          aria-label="Sonuç panelini kapat"
          onClick={() => onClose()}
        >
          <X size={16} />
        </button>
      </div>
      {resultTab === 'Computer' ? (
        <>
          <label className="computer-dot-picker">
            Şu Kit’in bilgisayarı
            <select
              value={computerDot?.id ?? ''}
              onChange={(event) => setComputerDotId(event.target.value)}
              aria-label="Kit bilgisayarını seç"
            >
              {dots.map((dot) => (
                <option key={dot.id} value={dot.id}>
                  {dot.name}
                </option>
              ))}
            </select>
          </label>
          {computerDot ? (
            <ComputerPanel key={computerDot.id} dot={computerDot} />
          ) : (
            <p className="computer-panel">
              Bilgisayar vermek için bir Kit oluştur.
            </p>
          )}
        </>
      ) : latest ? (
        <div className="result-content">
          <div className="result-meta">
            <span className="eyebrow">
              {latest.sample ? 'KURGUSAL ÖRNEK ÖZET' : 'ARAŞTIRMA ÖZETİ'}
            </span>
            <button
              className="icon-button"
              aria-label="Özeti indir"
              onClick={() => {
                const blob = new Blob(
                  [
                    latest.text +
                      '\n\nKaynaklar\n' +
                      latest.sources
                        .map((s) => `${s.title}: ${s.url}`)
                        .join('\n'),
                  ],
                  { type: 'text/plain' },
                );
                const url = URL.createObjectURL(blob);
                const anchor = document.createElement('a');
                anchor.href = url;
                anchor.download = 'kits-ozet.txt';
                anchor.click();
                URL.revokeObjectURL(url);
              }}
            >
              <ArrowDownToLine size={16} />
            </button>
          </div>
          {latest.sample && (
            <div className="sample-note">
              Kit’in neler yapabileceğine örnek. Aşağıdaki bulgular ve kaynaklar
              uydurmadır.
            </div>
          )}
          <article className="brief">
            <ReactMarkdown
              components={{
                img: ({ alt }) => (
                  <span>{alt ? `[Görsel: ${alt}]` : '[Görsel atlandı]'}</span>
                ),
                a: ({ children, href }) => (
                  <a href={href} target="_blank" rel="noreferrer">
                    {children}
                  </a>
                ),
              }}
            >
              {latest.text}
            </ReactMarkdown>
          </article>
          <section className="sources">
            <h3>
              Kaynak notları <span>{latest.sources.length}</span>
            </h3>
            {latest.sources.map((source) =>
              latest.sample ? (
                <div className="source-card" key={source.url}>
                  <span className="source-icon">
                    <BookOpen size={15} />
                  </span>
                  <div>
                    <strong>{source.title}</strong>
                    <p>{source.excerpt}</p>
                    <small>Kurgusal kaynak · canlı bağlantı değil</small>
                  </div>
                </div>
              ) : (
                <a
                  className="source-card"
                  href={source.url}
                  key={source.url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <span className="source-icon">
                    <ExternalLink size={15} />
                  </span>
                  <div>
                    <strong>{source.title}</strong>
                    <p>{source.excerpt}</p>
                    <small>{new URL(source.url).hostname}</small>
                  </div>
                  <ArrowUpRight size={15} />
                </a>
              ),
            )}
          </section>
        </div>
      ) : (
        <div className="pane-empty">
          <Mascot
            identity={defaultDotId}
            character={dots.find((dot) => dot.id === defaultDotId)?.character}
            name={dots.find((dot) => dot.id === defaultDotId)?.name}
            state={dotState}
          />
          <h3>Bulguların için küçük bir alan.</h3>
          <p>
            {status === 'failed'
              ? 'Araştırma özeti oluşturmak için hatayı giderip yeniden dene.'
              : 'Özetin ve kaynakların başarılı bir çalıştırmadan sonra burada görünür.'}
          </p>
        </div>
      )}
    </aside>
  );
}

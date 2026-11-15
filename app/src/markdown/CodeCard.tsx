import { memo, useEffect, useState } from "react";
import { canonicalLanguage, highlight, type HighlightedLine } from "./highlight";

/**
 * Kod kartı — kapalıyken ilk birkaç satır, açıkken tamamı.
 *
 * Uzun bir kod bloğunu olduğu gibi basmak sohbeti kullanılamaz hâle getiriyordu:
 * tek cevap ekranı doldurup önceki konuşmayı yukarı itiyordu. Kart kapalı
 * başlar, kullanıcı istediğinde açılır.
 *
 * Renklendirme ASENKRONDUR ve bekletmez: kod önce düz metin olarak çizilir,
 * token'lar geldiğinde yerine geçer. Renk gelene kadar boş kutu göstermek,
 * okunabilir bir içeriği hiç yokmuş gibi saklardı.
 */

import "./markdown.css";

/** Kapalı kartta görünen satır sayısı. */
const PREVIEW_LINES = 5;

/** Dil etiketi yoksa rozet yerine bu yazar. */
const PLAIN_LABEL = "metin";

export interface CodeCardProps {
  code: string;
  /** Model'in yazdığı ham dil etiketi; tanınmazsa yalnız rozet olarak görünür. */
  language?: string;
  /** Varsa başlıkta dosya adı gösterilir; kart tıklanınca bu dosya açılır. */
  filename?: string;
  /** Dosya adına tıklandığında çağrılır. Verilmezse ad düz metin kalır. */
  onOpenFile?: (path: string) => void;
}

/** Akış sırasında kod büyüdükçe her token'da yeniden renklendirme yapılmasın diye bekleme (U5-24). */
const HIGHLIGHT_DEBOUNCE_MS = 120;
/** Bundan uzun blok ana iş parçacığını tıkamasın: düz metin kalır (U5-24). */
const MAX_HIGHLIGHT_CHARS = 60_000;

function useHighlighted(code: string, language: string | undefined): HighlightedLine[] | null {
  // Sonuç, ÜRETİLDİĞİ kodla birlikte tutulur: kod değişince eski renkli satırlar yeni metnin yerine geçmez.
  const [result, setResult] = useState<{ code: string; lines: HighlightedLine[] | null } | null>(null);
  useEffect(() => {
    if (!language || code.length > MAX_HIGHLIGHT_CHARS) {
      setResult(null);
      return;
    }
    let active = true;
    const timer = window.setTimeout(() => {
      void highlight(code, language).then((lines) => {
        if (active) setResult({ code, lines });
      });
    }, HIGHLIGHT_DEBOUNCE_MS);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [code, language]);
  return result !== null && result.code === code ? result.lines : null;
}

/**
 * Token'ın iki temalı stilini React stiline çevir.
 *
 * shiki BİRİNCİ temayı düz `color` olarak verir, ikincisini `--shiki-dark`
 * değişkeni olarak. Düz `color` satır-içi stildir ve stil sayfasındaki koyu tema
 * kuralını EZER — o hâliyle koyu temada renkler hiç değişmezdi. İki tema da
 * özel değişkene alınır; `color`'a stil sayfası karar verir.
 */
function tokenStyle(token: HighlightedLine[number]): React.CSSProperties {
  const dual = (token as { htmlStyle?: Record<string, string> }).htmlStyle;
  const light = dual?.color ?? token.color;
  const dark = dual?.["--shiki-dark"] ?? light;
  if (!light) return {};
  return { "--shiki-light": light, "--shiki-dark": dark } as React.CSSProperties;
}

function CodeBody({ code, lines, limit }: {
  code: string;
  lines: HighlightedLine[] | null;
  limit: number | null;
}) {
  const plain = code.split("\n");
  const shown = lines ?? null;
  const count = limit ?? Number.POSITIVE_INFINITY;
  if (shown === null) {
    return <code>{plain.slice(0, count).join("\n")}</code>;
  }
  return (
    <code>
      {shown.slice(0, count).map((line, index) => (
        <span className="code-card__line" key={index}>
          {line.length === 0 ? "\n" : line.map((token, position) => (
            <span key={position} style={tokenStyle(token)}>{token.content}</span>
          ))}
          {index < Math.min(shown.length, count) - 1 && "\n"}
        </span>
      ))}
    </code>
  );
}

export const CodeCard = memo(function CodeCard({ code, filename, language, onOpenFile }: CodeCardProps) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const lines = useHighlighted(code, language);
  const total = code.split("\n").length;
  const collapsible = total > PREVIEW_LINES;
  const label = language ? (canonicalLanguage(language) ?? language) : PLAIN_LABEL;

  const copy = () => {
    void navigator.clipboard?.writeText(code).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      },
      () => setCopied(false),
    );
  };

  return (
    <figure className="code-card" data-open={open || !collapsible}>
      <figcaption className="code-card__head">
        {filename && onOpenFile ? (
          <button
            className="code-card__name code-card__name--link"
            onClick={() => onOpenFile(filename)}
            title={`${filename} dosyasını aç`}
            type="button"
          >
            {filename}
          </button>
        ) : (
          <span className="code-card__name">{filename ?? label}</span>
        )}
        {filename && <span className="code-card__lang">{label}</span>}
        <button
          aria-label="Kodu kopyala"
          className="code-card__copy"
          onClick={copy}
          type="button"
        >
          {copied ? "Kopyalandı" : "Kopyala"}
        </button>
      </figcaption>
      <div className="code-card__body">
        <pre>
          <CodeBody code={code} limit={open || !collapsible ? null : PREVIEW_LINES} lines={lines} />
        </pre>
      </div>
      {collapsible && (
        <button
          aria-expanded={open}
          className="code-card__toggle"
          onClick={() => setOpen((current) => !current)}
          type="button"
        >
          {open ? "Gizle" : `Kodu göster · ${total} satır`}
        </button>
      )}
    </figure>
  );
});

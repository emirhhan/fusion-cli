import { assetUrl } from "../platform/assetUrl";
import { Fragment, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { marked, type Token, type Tokens } from "marked";
import { CodeCard } from "./CodeCard";
import { classifyImageSource, safeLinkHref } from "./remoteContentPolicy";
import "./markdown.css";

/**
 * Model cevabını markdown olarak çizer.
 *
 * marked'ın ÜRETTİĞİ HTML KULLANILMAZ; yalnız lexer'ı kullanılır ve token ağacı
 * React elemanına çevrilir. Sebep RULES "XSS Prevention": modelden gelen metin
 * güvenilmezdir ve `dangerouslySetInnerHTML` ile basılsaydı cevabın içine
 * gömülmüş bir `<script>` ya da `onerror` niteliği uygulamanın içinde çalışırdı.
 * Token yolunda böyle bir kapı yoktur — ham HTML de düz metin olarak görünür.
 *
 * Kod blokları ayrı bir bileşene (`CodeCard`) gider: katlanma, kopyalama ve
 * renklendirme oraya aittir.
 */

export interface MarkdownProps {
  text: string;
  /** Kod kartındaki dosya adına tıklanınca çağrılır. */
  onOpenFile?: (path: string) => void;
}

/** Dil etiketinden dosya adı ayıkla: ```python:oyun/Player.gd biçimi. */
function splitInfo(info: string): { language?: string; filename?: string } {
  const raw = info.trim();
  if (!raw) return {};
  const [language, ...rest] = raw.split(":");
  const filename = rest.join(":").trim();
  return { language: language.trim() || undefined, filename: filename || undefined };
}

function InlineTokens({ tokens, onOpenFile }: { tokens?: Token[]; onOpenFile?: (path: string) => void }) {
  if (!tokens) return null;
  return (
    <>
      {tokens.map((token, index) => (
        <Fragment key={index}>{renderInline(token, onOpenFile)}</Fragment>
      ))}
    </>
  );
}

function renderInline(token: Token, onOpenFile?: (path: string) => void): ReactNode {
  switch (token.type) {
    case "strong":
      return <strong><InlineTokens onOpenFile={onOpenFile} tokens={(token as Tokens.Strong).tokens} /></strong>;
    case "em":
      return <em><InlineTokens onOpenFile={onOpenFile} tokens={(token as Tokens.Em).tokens} /></em>;
    case "del":
      return <del><InlineTokens onOpenFile={onOpenFile} tokens={(token as Tokens.Del).tokens} /></del>;
    case "codespan":
      return <code className="markdown__inline-code">{(token as Tokens.Codespan).text}</code>;
    case "br":
      return <br />;
    case "html":
      // Only this inert inline tag is supported; all other HTML stays text.
      return /^<br\s*\/?\s*>$/i.test(token.raw.trim()) ? <br /> : token.raw;
    case "link": {
      const link = token as Tokens.Link;
      const href = safeLinkHref(link.href);
      const label = <InlineTokens onOpenFile={onOpenFile} tokens={link.tokens} />;
      // İzin listesi dışındaki şema (javascript:, data:, file:) bağlantı olmaz, metin kalır.
      if (href === null) return <span className="markdown__link-blocked">{label}</span>;
      return (
        <a href={href} rel="noreferrer noopener" target="_blank">
          {label}
        </a>
      );
    }
    case "image": {
      const image = token as Tokens.Image;
      return <MarkdownImage alt={image.text} href={image.href} />;
    }
    // Ham HTML ve kaçış dizileri DÜZ METİNDİR: render edilmez, gösterilir.
    default:
      return (token as Tokens.Text).text ?? "";
  }
}

function ListBlock({ token, onOpenFile }: { token: Tokens.List; onOpenFile?: (path: string) => void }) {
  const items = token.items.map((item, index) => (
    <li key={index}>
      {item.task && <input aria-label={item.checked ? "Tamamlandı" : "Tamamlanmadı"} checked={Boolean(item.checked)} disabled readOnly type="checkbox" />}
      <BlockTokens onOpenFile={onOpenFile} tokens={item.tokens} />
    </li>
  ));
  return token.ordered ? <ol start={Number(token.start) || 1}>{items}</ol> : <ul>{items}</ul>;
}

function TableBlock({ token, onOpenFile }: { token: Tokens.Table; onOpenFile?: (path: string) => void }) {
  return (
    <div className="markdown__table-scroll">
      <table>
        <thead>
          <tr>{token.header.map((cell, index) => (
            <th key={index} style={{ textAlign: token.align[index] ?? undefined }}>
              <InlineTokens onOpenFile={onOpenFile} tokens={cell.tokens} />
            </th>
          ))}</tr>
        </thead>
        <tbody>
          {token.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>{row.map((cell, index) => (
              <td key={index} style={{ textAlign: token.align[index] ?? undefined }}>
                <InlineTokens onOpenFile={onOpenFile} tokens={cell.tokens} />
              </td>
            ))}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderBlock(token: Token, onOpenFile?: (path: string) => void): ReactNode {
  switch (token.type) {
    case "heading": {
      const heading = token as Tokens.Heading;
      const Tag = `h${Math.min(heading.depth, 6)}` as "h1";
      return <Tag><InlineTokens onOpenFile={onOpenFile} tokens={heading.tokens} /></Tag>;
    }
    case "paragraph":
      return <p><InlineTokens onOpenFile={onOpenFile} tokens={(token as Tokens.Paragraph).tokens} /></p>;
    case "code": {
      const block = token as Tokens.Code;
      const { language, filename } = splitInfo(block.lang ?? "");
      return <CodeCard code={block.text} filename={filename} language={language} onOpenFile={onOpenFile} />;
    }
    case "list":
      return <ListBlock onOpenFile={onOpenFile} token={token as Tokens.List} />;
    case "table":
      return <TableBlock onOpenFile={onOpenFile} token={token as Tokens.Table} />;
    case "blockquote":
      return <blockquote><BlockTokens onOpenFile={onOpenFile} tokens={(token as Tokens.Blockquote).tokens} /></blockquote>;
    case "hr":
      return <hr />;
    case "space":
      return null;
    case "text": {
      const text = token as Tokens.Text;
      return text.tokens ? <InlineTokens onOpenFile={onOpenFile} tokens={text.tokens} /> : text.text;
    }
    // `html` dahil tanınmayan her şey düz metindir.
    default:
      return (token as Tokens.Text).raw ?? "";
  }
}

function BlockTokens({ tokens, onOpenFile }: { tokens: Token[]; onOpenFile?: (path: string) => void }) {
  return (
    <>
      {tokens.map((token, index) => (
        <Fragment key={index}>{renderBlock(token, onOpenFile)}</Fragment>
      ))}
    </>
  );
}

export function Markdown({ text, onOpenFile }: MarkdownProps) {
  // `gfm` tablo ve üstü-çizili için gerekli. `breaks` kapalı: model zaten iki
  // satırla paragraf ayırıyor, tek satır sonunu <br> saymak listeleri bozuyordu.
  // Akış sırasında yalnız metin değişince baştan ayrıştırılır; boş/eksik yanıt (undefined) çökertmez (U5-23).
  const tokens = useMemo(
    () => marked.lexer(typeof text === "string" ? text : "", { gfm: true, breaks: false }),
    [text],
  );
  return (
    <div className="markdown">
      <BlockTokens onOpenFile={onOpenFile} tokens={tokens} />
    </div>
  );
}

function MarkdownImage({ alt, href }: { alt: string; href: string }) {
  const decision = classifyImageSource(href, assetUrl);
  const [remoteAllowed, setRemoteAllowed] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    // Lightbox açılınca odak kapat düğmesine gider, Tab diyaloğun içinde kalır, kapanınca tetikleyiciye
    // dönülür (U5-27).
    const trigger = triggerRef.current;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
      else if (event.key === "Tab") { event.preventDefault(); closeRef.current?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (trigger?.isConnected) trigger.focus();
    };
  }, [open]);
  const label = alt || "Görsel";
  if (decision.kind === "blocked") return <span className="markdown__image-missing">🖼 {label}</span>;
  if (decision.kind === "remote" && !remoteAllowed) {
    // Uzak görsel istek atar ve adresine gömülü veriyi dışarı taşır: kullanıcı seçer.
    return (
      <button className="markdown__image-remote" onClick={() => setRemoteAllowed(true)} type="button">
        🖼 {label} — uzak görseli yükle ({decision.host})
      </button>
    );
  }
  const src = decision.src;
  // Yüklenemeyen görsel boş şeffaf kutu bırakmaz: alt metinle açıkça gösterilir (U5-27).
  if (failed) return <span className="markdown__image-missing" role="img" aria-label={`${label} (yüklenemedi)`}>🖼 {label} — yüklenemedi</span>;
  return (
    <>
      <button
        aria-label={`${label} — büyüt`}
        className="markdown__image-button"
        data-loaded={loaded}
        onClick={() => setOpen(true)}
        ref={triggerRef}
        type="button"
      >
        <img
          alt={alt}
          className="markdown__image"
          loading="lazy"
          onError={() => setFailed(true)}
          onLoad={() => setLoaded(true)}
          referrerPolicy="no-referrer"
          src={src}
        />
      </button>
      {open && (
        <div
          aria-label={label}
          aria-modal="true"
          className="markdown__lightbox"
          onClick={() => setOpen(false)}
          role="dialog"
        >
          <img alt={alt} referrerPolicy="no-referrer" src={src} />
          <button
            aria-label="Kapat"
            className="markdown__lightbox-close"
            onClick={(event) => { event.stopPropagation(); setOpen(false); }}
            ref={closeRef}
            type="button"
          >
            ✕
          </button>
        </div>
      )}
    </>
  );
}

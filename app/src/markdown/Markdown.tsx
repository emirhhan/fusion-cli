import { Fragment, type ReactNode } from "react";
import { marked, type Token, type Tokens } from "marked";
import { CodeCard } from "./CodeCard";
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
    case "link": {
      const link = token as Tokens.Link;
      return (
        <a href={link.href} rel="noreferrer noopener" target="_blank">
          <InlineTokens onOpenFile={onOpenFile} tokens={link.tokens} />
        </a>
      );
    }
    case "image": {
      const image = token as Tokens.Image;
      return <img alt={image.text} className="markdown__image" src={image.href} />;
    }
    // Ham HTML ve kaçış dizileri DÜZ METİNDİR: render edilmez, gösterilir.
    default:
      return (token as Tokens.Text).text ?? "";
  }
}

function ListBlock({ token, onOpenFile }: { token: Tokens.List; onOpenFile?: (path: string) => void }) {
  const items = token.items.map((item, index) => (
    <li key={index}>
      {item.task && <input checked={Boolean(item.checked)} disabled type="checkbox" />}
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
  const tokens = marked.lexer(text, { gfm: true, breaks: false });
  return (
    <div className="markdown">
      <BlockTokens onOpenFile={onOpenFile} tokens={tokens} />
    </div>
  );
}

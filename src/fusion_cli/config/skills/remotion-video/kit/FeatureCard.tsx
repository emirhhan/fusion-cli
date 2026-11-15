import React, { useLayoutEffect, useRef, useState } from "react";
import { interpolate, spring, useCurrentFrame, useDelayRender, useVideoConfig } from "remotion";
import { theme } from "./theme";

// Kart başlığı 52 px'tir; en uzun sözcük sığmıyorsa 2 px adımla 44 px'e (destek metni
// tabanı) kadar küçülür. Ölçüldü (30 Ekim): uzun Türkçe sözcük ("Kullanılabilirlik")
// 3 sütunda ortadan bölünüyor, LayoutAudit bunu kusur sayıp render'ı durduruyordu.
// 44 px'te de sığmayan sözcük bölünür ve denetim metni kısaltmayı ister.
const TITLE_FONT = 52;
const TITLE_FONT_MIN = 44;
const fitTitle = (node: HTMLElement): number => {
  const {overflowWrap, fontSize} = node.style;
  node.style.overflowWrap = "normal";
  let size = TITLE_FONT;
  for (; size > TITLE_FONT_MIN; size -= 2) {
    node.style.fontSize = `${size}px`;
    if (node.scrollWidth <= node.clientWidth) break;
  }
  node.style.overflowWrap = overflowWrap;
  node.style.fontSize = fontSize;
  return size;
};

// 3B açıyla dönerek gelen cam kart. index ile sırayla gelir; ışık kenarı süzülür.
export const FeatureCard: React.FC<{ title: string; body?: string; icon?: string; index?: number; delay?: number; width?: number; bodyFontSize?: number; wrapText?: boolean }> = ({
  title, body, icon, index = 0, delay = 0, width = 520, bodyFontSize = 34, wrapText = false,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const titleNode = useRef<HTMLDivElement>(null);
  const [titleFont, setTitleFont] = useState(TITLE_FONT);
  const { delayRender, continueRender } = useDelayRender();
  useLayoutEffect(() => {
    if (!wrapText) return;
    const handle = delayRender("Kart başlığı sığdırılıyor");
    let active = true;
    const apply = () => { if (active && titleNode.current) setTitleFont(fitTitle(titleNode.current)); };
    apply();
    // Son font metrikleri gelince yeniden ölç; karar yarım kalmış fontla verilmesin.
    document.fonts.ready.then(() => { apply(); continueRender(handle); });
    return () => { active = false; continueRender(handle); };
  }, [title, width, wrapText, delayRender, continueRender]);
  const s = spring({ frame: frame - delay - index * 6, fps, config: { damping: 15, mass: 0.7 } });
  const shine = interpolate((frame - index * 6) % 120, [0, 120], [-100, 200]);
  return (
    <div style={{ perspective: 1400 }}>
      <div data-fusion-content={title} style={{
        boxSizing: "border-box", width, padding: "40px 44px", borderRadius: 28, position: "relative", overflow: "hidden",
        background: "linear-gradient(145deg, rgba(255,255,255,0.10), rgba(255,255,255,0.03))",
        border: "1.5px solid rgba(255,255,255,0.16)", boxShadow: `0 30px 80px rgba(0,0,0,0.45), 0 0 60px ${theme.accent2}22`,
        transform: `rotateY(${(1 - s) * 55}deg) translateY(${(1 - s) * 80}px) scale(${0.9 + 0.1 * s})`, opacity: s,
        fontFamily: theme.font, color: theme.text, overflowWrap: wrapText ? "break-word" : "normal", wordBreak: "normal",
      }}>
        <div style={{ position: "absolute", inset: 0, background: `linear-gradient(110deg, transparent ${shine - 20}%, rgba(255,255,255,0.12) ${shine}%, transparent ${shine + 20}%)` }} />
        {icon && <div style={{ fontSize: 64, marginBottom: 18 }}>{icon}</div>}
        <div ref={titleNode} data-fusion-card-title style={{ fontSize: titleFont, fontWeight: 750, letterSpacing: -1 }}>{title}</div>
        {body && <div data-fusion-feature-body style={{ fontSize: bodyFontSize, color: theme.muted, marginTop: 14, lineHeight: 1.3 }}>{inlineCode(body)}</div>}
      </div>
    </div>
  );
};

// `komut` biçimindeki parçaları kod etiketi olarak çiz; ham ters tırnak ekranda görünmesin.
// Ölçüldü (8 Ekim 2026, dalga43): kartlarda "`fusion serve`" ham haliyle görünüyordu.
export const inlineCode = (text: string): React.ReactNode[] =>
  text.split(/(`[^`]+`)/g).filter(Boolean).map((part, i) =>
    part.startsWith("`") && part.endsWith("`") && part.length > 2
      ? <code key={i} style={{ fontFamily: "'SF Mono', Menlo, monospace", fontSize: "0.88em", color: theme.text,
          background: "rgba(255,255,255,0.10)", border: "1px solid rgba(255,255,255,0.14)", borderRadius: 8,
          padding: "0.05em 0.35em" }}>{part.slice(1, -1)}</code>
      : <React.Fragment key={i}>{part}</React.Fragment>);

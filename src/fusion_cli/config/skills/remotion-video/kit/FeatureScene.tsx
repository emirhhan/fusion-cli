import React, {useLayoutEffect, useRef} from "react";
import {useCurrentFrame, useDelayRender, useVideoConfig} from "remotion";
import {CameraPush, Parallax} from "./CameraPush";
import {FeatureCard} from "./FeatureCard";
import {layoutPolicy} from "./layout";
import {featureSceneInset} from "./motion";
import {theme} from "./theme";
import {SceneFade} from "./Transition";

export type FeatureSceneCard = {title: string; body: string; icon?: string};
export type FeatureSceneProps = {
  title: string;
  subtitle?: string;
  cards: readonly [FeatureSceneCard] | readonly [FeatureSceneCard, FeatureSceneCard] | readonly [FeatureSceneCard, FeatureSceneCard, FeatureSceneCard];
};
const sceneTypography = {title: 96, supporting: 44, titleLeading: 1.1, supportingLeading: 1.3};
const sceneSpacing = {headingGap: 20, cardsGap: 32, columnGap: 24};

// Sahne API'si dıştan kamera eklenmeden kullanılır: bütçe kendi dönüşümlerini kapsar.
export const FeatureScene: React.FC<FeatureSceneProps> = ({title, subtitle, cards}) => {
  const {width, height} = useVideoConfig();
  const frame = useCurrentFrame();
  const horizontalInset = featureSceneInset(width, layoutPolicy.safeMargin);
  const verticalInset = featureSceneInset(height, layoutPolicy.safeMargin, true);
  const availableWidth = width - horizontalInset * 2;
  const availableHeight = height - verticalInset * 2;
  const content = useRef<HTMLDivElement>(null);
  const {delayRender, continueRender, cancelRender} = useDelayRender();
  if (cards.length < 1 || cards.length > 3) throw new Error("FeatureScene 1–3 kart alır; içeriği sahnelere böl.");
  if (availableWidth <= 0 || availableHeight <= 0) throw new Error("FeatureScene çözünürlüğünde güvenli içerik alanı yok; daha büyük tuval kullan.");
  if (!title.trim() || cards.some(card => !card.title.trim() || !card.body.trim())) {
    throw new Error("FeatureScene başlığı ve kart içerikleri boş olamaz.");
  }
  useLayoutEffect(() => {
    const handle = delayRender("Özellik sahnesinin doğal yüksekliği ölçülüyor");
    let active = true;
    let request = 0;
    const measure = () => {
      if (!active || !content.current) return;
      if (!content.current.clientWidth) {request = requestAnimationFrame(measure); return;}
      try {
        if (content.current.offsetHeight > availableHeight) {
          cancelRender(new Error("FeatureScene doğal metin yüksekliği güvenli alana sığmıyor; içeriği sahnelere böl. Font küçültme veya kırpma uygulama."));
        } else {
          content.current.setAttribute("data-fusion-feature-ready", "");
        }
      } finally {continueRender(handle);}
    };
    // offsetHeight doğal akış kutusudur; scrollHeight girişteki translateY
    // taşmasını da sayar ve sığan içeriği yanlış reddeder. Hareket taşmasını
    // sahnenin gerçek DOM LayoutAudit kapısı ayrıca ölçer.
    // Son font metrikleri gelmeden sığdı kararını verme. Giriş/çıkış karelerinde
    // de içerik bütçesi ölçülür; SceneFade'ın gerçek DOM kapısı ayrıca korunur.
    document.fonts.ready.then(() => {if (active) request = requestAnimationFrame(measure);});
    return () => {active = false; cancelAnimationFrame(request); continueRender(handle);};
  }, [frame, width, height, title, subtitle, cards, availableWidth, availableHeight, delayRender, continueRender, cancelRender]);
  const cardWidth = (availableWidth - sceneSpacing.columnGap * (cards.length - 1)) / cards.length;
  return <SceneFade><CameraPush><div style={{position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center"}}>
    <Parallax depth={0.5}><div ref={content} style={{width: availableWidth, display: "flex", flexDirection: "column", gap: sceneSpacing.cardsGap, fontFamily: theme.font, color: theme.text}}>
      <div style={{display: "flex", flexDirection: "column", gap: sceneSpacing.headingGap, textAlign: "center"}}>
        <div data-fusion-content={title} style={{fontSize: sceneTypography.title, fontWeight: 800, lineHeight: sceneTypography.titleLeading, overflowWrap: "anywhere"}}>{title}</div>
        {subtitle && <div data-fusion-content={subtitle} style={{fontSize: sceneTypography.supporting, lineHeight: sceneTypography.supportingLeading, color: theme.muted, overflowWrap: "anywhere"}}>{subtitle}</div>}
      </div>
      <div data-fusion-feature-cards style={{display: "grid", gridTemplateColumns: `repeat(${cards.length}, minmax(0, 1fr))`, gap: sceneSpacing.columnGap}}>
        {cards.map((card, index) => <FeatureCard key={index} {...card} index={index} width={cardWidth} bodyFontSize={sceneTypography.supporting} wrapText/>)}
      </div>
    </div></Parallax>
  </div></CameraPush></SceneFade>;
};

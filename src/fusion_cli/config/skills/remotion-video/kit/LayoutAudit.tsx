import React, {useLayoutEffect, useRef} from "react";
import {AbsoluteFill, useCurrentFrame, useDelayRender, useVideoConfig} from "remotion";
import {publishRuntime} from "./RuntimeEvidence";
import {ContentRect, inspectLayoutEvidence, LayoutFinding, layoutPolicy} from "./layout";

const opacityOf = (element: Element, root: Element): number => {
  let opacity = 1;
  for (let current: Element | null = element; current; current = current.parentElement) {
    const style = getComputedStyle(current);
    if (style.display === "none" || style.visibility === "hidden") return 0;
    opacity *= Number(style.opacity);
    if (current === root) break;
  }
  return opacity;
};

const contentRects = (root: HTMLElement, width: number, height: number): ContentRect[] => {
  const canvas = root.closest<HTMLElement>("[data-fusion-canvas]") ?? document.getElementById("remotion-canvas") ?? root;
  const bounds = canvas.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return [];
  const rectangles: ContentRect[] = [];
  root.querySelectorAll<HTMLElement>("[data-fusion-content]").forEach((element) => {
    if (opacityOf(element, root) < layoutPolicy.minOpacity) return;
    // Grupların içine işaretli bileşen konduysa yaprakları ölç: grup içindeki
    // başlık/kart çakışmasını yutma; aynı içeriği iki kez de sayma.
    if (element.querySelector("[data-fusion-content]")) return;
    const parts = element.hasAttribute("data-fusion-text")
      ? Array.from(element.children).filter(child => opacityOf(child, root) >= layoutPolicy.minOpacity)
      : [element];
    const visible = parts.map(part => part.getBoundingClientRect()).filter(rect => rect.width && rect.height);
    if (!visible.length) return;
    rectangles.push({
      label: element.dataset.fusionContent ?? "İçerik",
      left: (Math.min(...visible.map(rect => rect.left)) - bounds.left) * width / bounds.width,
      top: (Math.min(...visible.map(rect => rect.top)) - bounds.top) * height / bounds.height,
      right: (Math.max(...visible.map(rect => rect.right)) - bounds.left) * width / bounds.width,
      bottom: (Math.max(...visible.map(rect => rect.bottom)) - bounds.top) * height / bounds.height,
    });
  });
  return rectangles;
};

// Görünürlük zarfı: tuvalle kesişmeyen veya tolerans kadar ince kalan kutu
// anlamlı içerik sayılmaz. Kısmi kesişim metin okunurluğu kanıtı değildir;
// güvenli alan/taşma kontrolü yerel geometri kapısında ayrıca korunur.
const visibleContentRects = (root: HTMLElement, width: number, height: number): ContentRect[] =>
  contentRects(root, width, height).filter(rect =>
    Math.min(width, rect.right) - Math.max(0, rect.left) > layoutPolicy.overlapTolerance &&
    Math.min(height, rect.bottom) - Math.max(0, rect.top) > layoutPolicy.overlapTolerance);

const measuredFindings = (root: HTMLElement, width: number, height: number, margin: number, scope: "local" | "composition"): LayoutFinding[] => {
  const rectangles = scope === "composition" ? visibleContentRects(root, width, height) : contentRects(root, width, height);
  const findings: LayoutFinding[] = scope === "local" ? inspectLayoutEvidence(rectangles, {width, height}, margin)
    : rectangles.length ? [] : [{family: "empty", message: "Composition karesinde okunabilir içerik yok."}];
  if (scope === "composition") {
    const readableScenes = Array.from(root.querySelectorAll<HTMLElement>("[data-fusion-scene]"))
      .filter(scene => opacityOf(scene, root) >= layoutPolicy.minOpacity && visibleContentRects(scene, width, height).length > 0);
    if (readableScenes.length !== 1) findings.push({family: readableScenes.length ? "overlap" : "empty", message: "Composition karesinde tam bir okunabilir sahne olmalı; boşluk/örtüşme var."});
  }
  return findings;
};

// Her Sequence İÇİNDE kullan: useCurrentFrame yerel sahne karesidir. İlk 1 sn girişe,
// son yarım saniye çıkışa ayrılır; aradaki HER render karesinde gerçek DOM ölçülür.
export const LayoutAudit: React.FC<{children: React.ReactNode; margin?: number; scope?: "local" | "composition"}> = ({children, margin = layoutPolicy.safeMargin, scope = "local"}) => {
  const root = useRef<HTMLDivElement>(null);
  const frame = useCurrentFrame();
  const {width, height, fps, durationInFrames} = useVideoConfig();
  const {delayRender, continueRender, cancelRender} = useDelayRender();
  useLayoutEffect(() => {
    if (!root.current) return;
    const globalFrame = root.current.closest<HTMLElement>("[data-fusion-timeline]")?.dataset.fusionRuntimeFrame ?? String(frame);
    root.current.dataset.fusionAuditFrame = globalFrame;
    root.current.dataset.fusionAuditState = "pending";
    if (scope === "local" && (frame < fps || frame >= durationInFrames - fps / 2)) {
      root.current.dataset.fusionAuditState = "grace"; return;
    }
    // Remotion önce ekran dışı portalı kurar, ardından tuvale taşır. Ölçümü bir
    // çizim turu beklet; render da denetim bitmeden ekran görüntüsü alamaz.
    const handle = delayRender("Sahne yerleşimi ölçülüyor");
    let request: number;
    const measure = () => {
      if (!root.current) {continueRender(handle); return;}
      const bounds = root.current.getBoundingClientRect();
      if (!bounds.width || !bounds.height) {
        request = requestAnimationFrame(measure);
        return;
      }
      try {
        const findings = measuredFindings(root.current, width, height, margin, scope);
        root.current.dataset.fusionAuditState = findings.length ? "failed" : "settled";
        if (findings.length) {
          publishRuntime(root.current, findings.map(finding => finding.message));
          // Sürümlü araç protokolü: aile gerçek ölçümden gelir, hata metninden tahmin edilmez.
          console.error("FUSION_FAILURE_V1:" + JSON.stringify({version: 1, families: [...new Set(findings.map(finding => finding.family))]}));
          cancelRender(new Error(`Yerleşim denetimi, kare ${frame}: ${findings.slice(0, 5).map(finding => finding.message).join(" ")}`));
        }
      } finally {
        continueRender(handle);
      }
    };
    request = requestAnimationFrame(measure);
    return () => {cancelAnimationFrame(request); continueRender(handle);};
  }, [frame, width, height, fps, durationInFrames, margin, scope, delayRender, continueRender, cancelRender]);
  return <AbsoluteFill ref={root} data-fusion-audit-scope={scope}>{children}</AbsoluteFill>;
};

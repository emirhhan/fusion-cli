import React, {useLayoutEffect, useRef} from "react";
import {getInputProps, useCurrentFrame, useDelayRender, useVideoConfig} from "remotion";

const PREFIX = "FUSION_RUNTIME_V1:";
const sessionOf = (): string | null => {
  const value = getInputProps().__fusionRuntimeSession;
  return typeof value === "string" && value.trim() ? value : null;
};

export const publishRuntime = (element: HTMLElement, findings: readonly string[] = []): void => {
  const root = element.matches("[data-fusion-timeline]") ? element : element.closest<HTMLElement>("[data-fusion-timeline]") ?? element.querySelector<HTMLElement>("[data-fusion-timeline]");
  const session = sessionOf();
  if (!root || !session) return;
  const audits = [root.closest<HTMLElement>('[data-fusion-audit-scope="composition"]'), ...Array.from(root.querySelectorAll<HTMLElement>("[data-fusion-audit-scope]"))].filter((audit): audit is HTMLElement => audit !== null);
  const frame = root.dataset.fusionRuntimeFrame;
  const settled = audits.length > 0 && audits.every(audit => audit.dataset.fusionAuditFrame === frame && ["settled", "grace"].includes(audit.dataset.fusionAuditState ?? ""));
  const features = Array.from(root.querySelectorAll<HTMLElement>("[data-fusion-feature-scene]"));
  console.log(PREFIX + JSON.stringify({
    session, composition: root.dataset.fusionRuntimeComposition, frame: Number(frame),
    activeScenes: Array.from(root.querySelectorAll<HTMLElement>("[data-fusion-scene]")).map(scene => scene.dataset.fusionScene),
    activeSceneKinds: Array.from(root.querySelectorAll<HTMLElement>("[data-fusion-scene]")).map(scene => scene.dataset.fusionSceneKind ?? ""),
    featureReady: features.length > 0 && features.every(feature => feature.getAttribute("data-fusion-feature-ready") === frame),
    auditSettled: settled && findings.length === 0, findings, runtimeExecuted: true, timelineSeen: true,
  }));
};

// Ayrı delayRender sahibi kayıt hazır olmadan still'in tamamlanmasını önler.
export const RuntimeEvidence: React.FC<{children: React.ReactNode}> = ({children}) => {
  const root = useRef<HTMLDivElement>(null);
  const frame = useCurrentFrame();
  const {id} = useVideoConfig();
  const {delayRender, continueRender} = useDelayRender();
  useLayoutEffect(() => {
    if (!sessionOf()) return;
    const handle = delayRender("Runtime kare kanıtı bekleniyor");
    let request = 0;
    const measure = () => {
      if (!root.current) {continueRender(handle); return;}
      const audits = [root.current.closest<HTMLElement>('[data-fusion-audit-scope="composition"]'), ...Array.from(root.current.querySelectorAll<HTMLElement>("[data-fusion-audit-scope]"))].filter((audit): audit is HTMLElement => audit !== null);
      const features = Array.from(root.current.querySelectorAll<HTMLElement>("[data-fusion-feature-scene]"));
      if (audits.some(audit => audit.dataset.fusionAuditFrame !== String(frame) || !["settled", "grace"].includes(audit.dataset.fusionAuditState ?? "")) || features.some(feature => feature.getAttribute("data-fusion-feature-ready") !== String(frame))) {
        request = requestAnimationFrame(measure); return;
      }
      publishRuntime(root.current);
      continueRender(handle);
    };
    request = requestAnimationFrame(measure);
    return () => {cancelAnimationFrame(request); continueRender(handle);};
  }, [frame, id, delayRender, continueRender]);
  return <div ref={root} data-fusion-timeline data-fusion-runtime-frame={frame} data-fusion-runtime-composition={id} style={{position: "absolute", inset: 0}}>{children}</div>;
};

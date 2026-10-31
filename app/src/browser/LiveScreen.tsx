import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type WheelEvent } from "react";
import {
  HOVER_THROTTLE_MS,
  SCROLL_FLUSH_MS,
  keyAction,
  normalizedPoint,
  type Box,
  type BrowserFrame,
} from "./browserPanelProtocol";

/**
 * Paylaşılan tarayıcının canlı görüntüsü ve girdisi (P-045).
 *
 * Görüntü çekirdeğin ekran yayınından gelen JPEG'dir; tıklama, tekerlek ve klavye görüntünün
 * 0..1 koordinatına çevrilip çekirdeğe gider. Öğe seçici açıkken (P-041) tıklama sayfaya
 * GİTMEZ: imlecin altındaki öğe vurgulanır, tıklanınca seçilir.
 */
export interface LiveScreenProps {
  frame: BrowserFrame;
  title: string;
  picking: boolean;
  onClick: (x: number, y: number, clicks: number) => void;
  onScroll: (x: number, y: number, dx: number, dy: number) => void;
  onType: (text: string) => void;
  onKey: (key: string) => void;
  onHover: (x: number, y: number) => Promise<Box | null>;
  onPick: (x: number, y: number) => void;
}

export function LiveScreen({ frame, title, picking, onClick, onScroll, onType, onKey, onHover, onPick }: LiveScreenProps) {
  const image = useRef<HTMLImageElement | null>(null);
  const [box, setBox] = useState<Box | null>(null);
  const hoverAt = useRef(0);
  const wheel = useRef<{ x: number; y: number; dx: number; dy: number; timer?: number }>({ x: 0, y: 0, dx: 0, dy: 0 });

  useEffect(() => { if (!picking) setBox(null); }, [picking]);
  useEffect(() => () => { if (wheel.current.timer) window.clearTimeout(wheel.current.timer); }, []);

  const point = (event: { clientX: number; clientY: number }) => {
    const rect = image.current?.getBoundingClientRect();
    return rect ? normalizedPoint(event.clientX, event.clientY, rect) : null;
  };

  const handleClick = (event: MouseEvent<HTMLImageElement>) => {
    event.preventDefault();
    event.currentTarget.parentElement?.focus();
    const at = point(event);
    if (!at) return;
    if (picking) onPick(at.x, at.y);
    else onClick(at.x, at.y, event.detail >= 2 ? 2 : 1);
  };

  const handleMove = (event: MouseEvent<HTMLImageElement>) => {
    if (!picking) return;
    const now = Date.now();
    if (now - hoverAt.current < HOVER_THROTTLE_MS) return;
    hoverAt.current = now;
    const at = point(event);
    if (at) void onHover(at.x, at.y).then(setBox).catch(() => setBox(null));
  };

  const handleWheel = (event: WheelEvent<HTMLDivElement>) => {
    const at = point(event);
    if (!at) return;
    const pending = wheel.current;
    pending.x = at.x;
    pending.y = at.y;
    pending.dx += event.deltaX;
    pending.dy += event.deltaY;
    if (pending.timer) return;
    pending.timer = window.setTimeout(() => {
      const { x, y, dx, dy } = wheel.current;
      wheel.current = { x, y, dx: 0, dy: 0 };
      if (dx || dy) onScroll(x, y, dx, dy);
    }, SCROLL_FLUSH_MS);
  };

  const handleKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const action = keyAction(event);
    if (!action) return;
    event.preventDefault();
    if (action.tur === "yaz") onType(action.metin);
    else onKey(action.tus);
  };

  return (
    <div
      aria-label={`Canlı sayfa: ${title || "adsız sayfa"}. Tıkla, kaydır ya da yaz; girdi sayfaya gider.`}
      className="browser-live"
      data-picking={picking}
      onKeyDown={handleKey}
      onPaste={(event) => {
        const text = event.clipboardData.getData("text");
        if (text) { event.preventDefault(); onType(text); }
      }}
      onWheel={handleWheel}
      role="application"
      tabIndex={0}
    >
      <img
        alt={title ? `${title} canlı görüntüsü` : "Sayfanın canlı görüntüsü"}
        className="browser-live__image"
        draggable={false}
        onClick={handleClick}
        onContextMenu={(event) => event.preventDefault()}
        onMouseLeave={() => setBox(null)}
        onMouseMove={handleMove}
        ref={image}
        src={`data:${frame.mime};base64,${frame.base64}`}
      />
      {picking && box && (
        <span
          aria-hidden="true"
          className="browser-live__highlight"
          data-testid="browser-pick-highlight"
          style={{
            height: `${box.h * 100}%`,
            left: `${box.x * 100}%`,
            top: `${box.y * 100}%`,
            width: `${box.w * 100}%`,
          }}
        />
      )}
    </div>
  );
}

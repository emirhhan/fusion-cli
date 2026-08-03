import React from "react";
import { useCurrentFrame, interpolate, spring, useVideoConfig } from "remotion";
import { theme } from "../theme";

export type Line =
  | { kind: "cmd"; text: string; at: number }
  | { kind: "out"; text: string; at: number; color?: string }
  | { kind: "comment"; text: string; at: number }
  | { kind: "gap"; at: number };

const CHARS_PER_FRAME = 1.7;

const lineColor = (line: Line): string => {
  if (line.kind === "comment") return theme.faint;
  if (line.kind === "out") return line.color ?? theme.dim;
  return theme.text;
};

const Cursor: React.FC = () => {
  const frame = useCurrentFrame();
  const on = Math.floor(frame / 15) % 2 === 0;
  return (
    <span style={{ opacity: on ? 1 : 0, color: theme.accent }}>▋</span>
  );
};

const TerminalLine: React.FC<{ line: Line; active: boolean }> = ({ line, active }) => {
  const frame = useCurrentFrame();
  if (line.kind === "gap") return <div style={{ height: 18 }} />;

  const elapsed = Math.max(0, frame - line.at);
  const isCmd = line.kind === "cmd";
  const shown = isCmd
    ? line.text.slice(0, Math.floor(elapsed * CHARS_PER_FRAME))
    : line.text;
  const revealed = !isCmd ? Math.min(1, elapsed / 8) : 1;
  const typing = isCmd && shown.length < line.text.length;

  return (
    <div
      style={{
        fontFamily: theme.fontMono,
        fontSize: 30,
        lineHeight: 1.55,
        color: lineColor(line),
        opacity: isCmd ? 1 : revealed,
        whiteSpace: "pre-wrap",
      }}
    >
      {line.kind === "comment" && <span>{"# "}</span>}
      {isCmd && <span style={{ color: theme.accent2, fontWeight: 700 }}>{"❯ "}</span>}
      <span>{shown}</span>
      {typing && active && <Cursor />}
    </div>
  );
};

export const Terminal: React.FC<{
  title?: string;
  lines: Line[];
  width?: number;
}> = ({ title = "fusion — terminal", lines, width = 1200 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 200 } });
  const lastActiveAt = Math.max(...lines.map((l) => l.at), 0);

  return (
    <div
      style={{
        width,
        borderRadius: 18,
        overflow: "hidden",
        background: theme.surface,
        border: `1px solid ${theme.surfaceBorder}`,
        boxShadow: "0 40px 120px rgba(0,0,0,0.55)",
        opacity: enter,
        transform: `translateY(${interpolate(enter, [0, 1], [40, 0])}px) scale(${interpolate(
          enter,
          [0, 1],
          [0.97, 1]
        )})`,
      }}
    >
      <div
        style={{
          height: 56,
          background: theme.terminalBar,
          display: "flex",
          alignItems: "center",
          padding: "0 22px",
          gap: 12,
          borderBottom: `1px solid ${theme.surfaceBorder}`,
        }}
      >
        {[theme.red, theme.yellow, theme.green].map((c) => (
          <span
            key={c}
            style={{ width: 15, height: 15, borderRadius: 999, background: c }}
          />
        ))}
        <span
          style={{
            marginLeft: 14,
            fontFamily: theme.fontMono,
            fontSize: 24,
            color: theme.dim,
          }}
        >
          {title}
        </span>
      </div>
      <div style={{ padding: "30px 36px", minHeight: 120 }}>
        {lines.map((line, i) => (
          <TerminalLine key={i} line={line} active={line.at >= lastActiveAt} />
        ))}
      </div>
    </div>
  );
};

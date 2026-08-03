// Fusion kimliği: turuncu → pembe gradyan (ürünün banner geçişiyle aynı), koyu terminal.
// Renk/ölçü değerleri TEK yerde; sahnelerde hex dağıtılmaz.

export const theme = {
  bg: "#0b0b10",
  bgGradient: "radial-gradient(120% 120% at 50% 0%, #16121e 0%, #0b0b10 55%)",
  surface: "#14141c",
  surfaceBorder: "#262633",
  terminalBar: "#1b1b25",
  text: "#e9e9f2",
  dim: "#8b8ba3",
  faint: "#5a5a72",
  accent: "#ff8a3d",
  accent2: "#ff4d8d",
  green: "#5ee2a0",
  blue: "#5aa9ff",
  yellow: "#ffd166",
  red: "#ff6b6b",
  gradient: "linear-gradient(100deg, #ff8a3d 0%, #ff5c7a 50%, #ff4d8d 100%)",
  fontMono:
    "'JetBrains Mono', 'SFMono-Regular', 'Menlo', 'Consolas', monospace",
  fontSans:
    "'Inter', -apple-system, 'Segoe UI', 'Helvetica Neue', sans-serif",
} as const;

// Video sabitleri
export const VIDEO = {
  width: 1920,
  height: 1080,
  fps: 30,
} as const;

// Fusion turuncu→pembe gradyanının bir satıra dağıtılmış hâli (picker'daki gibi).
export const gradientStops = ["#ff8a3d", "#ff7a52", "#ff6a66", "#ff5c7a", "#ff4d8d"];

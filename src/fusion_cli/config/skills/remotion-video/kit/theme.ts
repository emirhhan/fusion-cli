// Fusion hareket kiti — ortak tema. Renkleri burada değiştir; bileşenler buradan okur.
export const theme = {
  bg: "#06070d",
  bg2: "#0d1230",
  accent: "#7cf29a",
  accent2: "#5b8cff",
  accent3: "#c06bff",
  text: "#f4f6ff",
  muted: "#9aa3c7",
  font: "Inter, 'SF Pro Display', system-ui, sans-serif",
};

// Deterministik sözde-rastgele (aynı tohum = aynı kare; render tekrarlanabilir kalır).
export const seeded = (seed: number) => {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => (s = (s * 16807) % 2147483647) / 2147483647;
};

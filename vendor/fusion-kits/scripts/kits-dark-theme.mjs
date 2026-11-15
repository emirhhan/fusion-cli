// Kits arayüzünün koyu temasını açık temadan üretir.
// Kaynak stil dosyalarında yüzlerce sabit renk var; her birini elle çevirmek yerine
// renk taşıyan her bildirim Fusion'ın koyu paletine eşlenir ve
// `:root[data-theme="dark"]` altında ayrı bir dosyaya yazılır.
import { readFileSync, writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import process from 'node:process';
import postcss from 'postcss';
import { projectRoot } from './kits-start.mjs';

const SOURCES = ['style.css', 'editor.css', 'kits.css'];
const OUTPUT = 'kits-dark.generated.css';
const COLOR_PROPERTY =
  /^(color|background|background-color|background-image|border|border-(top|right|bottom|left)(-color)?|border-color|outline|outline-color|fill|stroke|caret-color|text-decoration|text-decoration-color|column-rule|accent-color|--[\w-]+)$/;
const COLOR_TOKEN = /#[0-9a-fA-F]{3,8}\b|rgba?\([^)]*\)|\b(white|black)\b/g;
// Fusion koyu teması (theme/tokens.css): zemin #212121, kenar çubuğu #181818.
const DARK_FLOOR = 0.13;
const DARK_RANGE = 0.8;

export function parseColor(token) {
  const value = token.trim().toLowerCase();
  if (value === 'white') return { r: 255, g: 255, b: 255, a: 1 };
  if (value === 'black') return { r: 0, g: 0, b: 0, a: 1 };
  if (value.startsWith('#')) {
    let hex = value.slice(1);
    if (hex.length === 3 || hex.length === 4)
      hex = [...hex].map((char) => char + char).join('');
    if (hex.length !== 6 && hex.length !== 8) return null;
    const number = (start) => Number.parseInt(hex.slice(start, start + 2), 16);
    return {
      r: number(0),
      g: number(2),
      b: number(4),
      a: hex.length === 8 ? number(6) / 255 : 1,
    };
  }
  const parts = value.match(/-?\d*\.?\d+%?/g);
  if (!parts || parts.length < 3) return null;
  const channel = (part) =>
    part.endsWith('%') ? (Number.parseFloat(part) * 255) / 100 : Number(part);
  const alpha = parts[3]
    ? parts[3].endsWith('%')
      ? Number.parseFloat(parts[3]) / 100
      : Number(parts[3])
    : 1;
  return {
    r: channel(parts[0]),
    g: channel(parts[1]),
    b: channel(parts[2]),
    a: alpha,
  };
}

function toHsl({ r, g, b }) {
  const [red, green, blue] = [r / 255, g / 255, b / 255];
  const max = Math.max(red, green, blue);
  const min = Math.min(red, green, blue);
  const l = (max + min) / 2;
  if (max === min) return { h: 0, s: 0, l };
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const h =
    max === red
      ? ((green - blue) / d + (green < blue ? 6 : 0)) / 6
      : max === green
        ? ((blue - red) / d + 2) / 6
        : ((red - green) / d + 4) / 6;
  return { h, s, l };
}

function fromHsl({ h, s, l }) {
  if (s === 0) return [l, l, l].map((value) => Math.round(value * 255));
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const hue = (t) => {
    const wrapped = (t + 1) % 1;
    if (wrapped < 1 / 6) return p + (q - p) * 6 * wrapped;
    if (wrapped < 1 / 2) return q;
    if (wrapped < 2 / 3) return p + (q - p) * (2 / 3 - wrapped) * 6;
    return p;
  };
  return [hue(h + 1 / 3), hue(h), hue(h - 1 / 3)].map((value) =>
    Math.round(value * 255),
  );
}

/** Açık temadaki rengin koyu temadaki karşılığı. */
export function darkColor(token) {
  const color = parseColor(token);
  if (!color) return token;
  const hsl = toHsl(color);
  let next;
  if (hsl.s < 0.12) {
    // Nötrler: beyaz zemin Fusion zeminine, koyu metin açık metne döner.
    next = { h: hsl.h, s: 0, l: DARK_FLOOR + (1 - hsl.l) * DARK_RANGE };
  } else if (hsl.l > 0.82) {
    // Açık renkli zeminler (vurgu kutuları): koyu, hafif renkli yüzey.
    next = { h: hsl.h, s: hsl.s * 0.45, l: 0.2 };
  } else if (hsl.l < 0.42) {
    // Koyu renkli metin ve çizgiler: koyu zeminde okunacak kadar açılır.
    next = { h: hsl.h, s: Math.min(hsl.s, 0.75), l: 0.72 };
  } else {
    next = hsl;
  }
  const [r, g, b] = fromHsl(next);
  return color.a < 1
    ? `rgb(${r} ${g} ${b} / ${Math.round(color.a * 100)}%)`
    : `#${[r, g, b].map((value) => value.toString(16).padStart(2, '0')).join('')}`;
}

export function darkValue(property, value) {
  // Gölgeler koyu temada da koyudur; çevrilirse parlak hale yapar.
  if (property === 'box-shadow' || property === 'text-shadow') return value;
  return value.replace(COLOR_TOKEN, (token) => darkColor(token));
}

function darkSelector(selector) {
  return selector
    .split(',')
    .map((part) => {
      const trimmed = part.trim();
      if (trimmed.startsWith(':root'))
        return `:root[data-theme="dark"]${trimmed.slice(5)}`;
      // Yalnız öğe seçicisi (`button`, `textarea:focus`): koyu kök önekinin
      // seçiciliği eklenmez; yoksa açık temada sınıfla ezilen genel kural
      // koyu temada sınıflı kuralları ezer (karşılamadaki düğmeler kutulaşıyordu).
      if (!/[.#[]/.test(trimmed))
        return `:where(:root[data-theme="dark"]) ${trimmed}`;
      return `:root[data-theme="dark"] ${trimmed}`;
    })
    .join(',\n');
}

export function darkStylesheet(css) {
  const output = postcss.root();
  const walk = (container, target) => {
    container.each((node) => {
      if (node.type === 'atrule') {
        if (/keyframes|font-face/.test(node.name)) return;
        const clone = postcss.atRule({ name: node.name, params: node.params });
        walk(node, clone);
        if (clone.nodes?.length) target.append(clone);
        return;
      }
      if (node.type !== 'rule') return;
      const rule = postcss.rule({ selector: darkSelector(node.selector) });
      node.each((declaration) => {
        if (
          declaration.type !== 'decl' ||
          !COLOR_PROPERTY.test(declaration.prop)
        )
          return;
        const value = darkValue(declaration.prop, declaration.value);
        if (value !== declaration.value)
          rule.append({
            prop: declaration.prop,
            value,
            important: declaration.important,
          });
      });
      if (rule.nodes?.length) target.append(rule);
    });
  };
  walk(postcss.parse(css), output);
  return output.toString();
}

function main() {
  const client = resolve(projectRoot, 'src/client');
  const manifest = JSON.parse(
    readFileSync(
      resolve(projectRoot, 'src/shared/fusion-brand-manifest.json'),
      'utf8',
    ),
  );
  const brand = readFileSync(
    resolve(client, 'fusion-brand.generated.css'),
    'utf8',
  );
  if (
    manifest.schemaVersion !== 1 ||
    createHash('sha256').update(brand).digest('hex') !== manifest.cssSha256
  )
    throw new Error(
      'Ortak marka token makbuzu doğrulanamadı; canonical kaynaktan yeniden üret.',
    );
  const source = SOURCES.map((file) =>
    readFileSync(resolve(client, file), 'utf8'),
  ).join('\n');
  const header =
    '/* ÜRETİLMİŞ DOSYA — elle düzenleme. Kaynak: scripts/kits-dark-theme.mjs */\n' +
    ':root[data-theme="dark"] {\n  color-scheme: dark;\n  --kits-signal: var(--fusion-cyan);\n}\n';
  // Fusion koyu temasında vurgu metni camgöbeğidir (açık temada koyu mavi).
  const accent = [
    ':root[data-theme="dark"] {',
    '  --kits-accent-text: var(--fusion-cyan);',
    '  --blue: var(--fusion-cyan);',
    '  --blue-dark: var(--fusion-cyan);',
    // Fusion theme/tokens.css koyu değerleri: zemin, kenar çubuğu, kenarlık, metin.
    '  --kits-ink: var(--fusion-ink);',
    '  --kits-dialog-surface: var(--fusion-dialog-surface);',
    '  --kits-dialog-border: var(--fusion-dialog-border);',
    '  --kits-input-surface: var(--fusion-input-surface);',
    '  --kits-muted: var(--fusion-muted);',
    '  --kits-sidebar: var(--fusion-sidebar);',
    '  --kits-border: #353535;',
    '  --kits-hover: #2a2a2a;',
    '  --kits-selected: #2f2f2f;',
    '  --ink: var(--fusion-ink);',
    '  --muted: var(--fusion-muted);',
    '  --line: #353535;',
    '  --document-ink: var(--fusion-ink);',
    '  --document-muted: var(--fusion-muted);',
    '  --document-line: #353535;',
    '  background: var(--fusion-canvas);',
    '  color: var(--fusion-ink);',
    '}',
    ':root[data-theme="dark"] body,',
    ':root[data-theme="dark"] .template-app {',
    '  background: var(--fusion-canvas);',
    '}',
    '',
  ].join('\n');
  writeFileSync(
    resolve(client, OUTPUT),
    `${header}${darkStylesheet(source)}\n${accent}`,
  );
  console.log(`Koyu tema üretildi: src/client/${OUTPUT}`);
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) ===
    resolve(projectRoot, 'scripts/kits-dark-theme.mjs')
)
  main();

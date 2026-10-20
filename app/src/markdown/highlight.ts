/**
 * Sözdizimi renklendirme — shiki çekirdeği, iki tema, tembel dil yüklemesi.
 *
 * HTML ÜRETİLMEZ. shiki'nin `codeToTokens` API'si yapılandırılmış token döndürür
 * ve renklendirme React elemanı olarak çizilir; modelden gelen metin hiçbir
 * noktada `innerHTML`'e verilmez (RULES "XSS Prevention").
 *
 * İki tema AYNI ANDA çözülür: her token'ın stili açık ve koyu karşılığını
 * birlikte taşır, hangisinin kullanılacağına CSS karar verir. Tek tema seçip
 * tema değişiminde yeniden renklendirmek, uzun sohbette her geçişte tüm
 * blokları yeniden çözmek demekti.
 *
 * PAKET BOYUTU — ölçüldü: hazır `shiki` girişi TÜM dilleri ve 622 kB'lık
 * Oniguruma wasm motorunu derlemeye sokuyordu (wolfram, emacs-lisp, typst…
 * hiçbiri bu üründe kullanılmıyor) ve hepsi masaüstü paketine giriyordu. Bu
 * yüzden çekirdek API + JavaScript regex motoru kullanılır ve diller AŞAĞIDAKİ
 * LİSTEDEN, tek tek, yalnız görüldüklerinde yüklenir.
 */

import type { ThemedToken } from "shiki";

/** Bir satırlık renklendirilmiş token dizisi. */
export type HighlightedLine = ThemedToken[];

/** Açık ve koyu tema adları — ikisi birden çözülür. */
export const LIGHT_THEME = "github-light";
export const DARK_THEME = "github-dark";

/**
 * Desteklenen diller: kanonik ad → grameri getiren tembel import.
 *
 * Liste bilinçli olarak dardır ve ürünün işine göre seçilmiştir (Godot işi için
 * `gdscript` dahil). Her giriş derlemede ayrı bir parça üretir; listede olmayan
 * bir dil renklendirilmez ama kod yine GÖSTERİLİR — tanınmayan bir dil yüzünden
 * içeriği gizlemek kullanıcıyı kör bırakırdı.
 */
const LANGUAGE_LOADERS: Record<string, () => Promise<unknown>> = {
  bash: () => import("@shikijs/langs/bash"),
  c: () => import("@shikijs/langs/c"),
  cpp: () => import("@shikijs/langs/cpp"),
  csharp: () => import("@shikijs/langs/csharp"),
  css: () => import("@shikijs/langs/css"),
  diff: () => import("@shikijs/langs/diff"),
  docker: () => import("@shikijs/langs/docker"),
  gdscript: () => import("@shikijs/langs/gdscript"),
  go: () => import("@shikijs/langs/go"),
  html: () => import("@shikijs/langs/html"),
  java: () => import("@shikijs/langs/java"),
  javascript: () => import("@shikijs/langs/javascript"),
  json: () => import("@shikijs/langs/json"),
  jsx: () => import("@shikijs/langs/jsx"),
  kotlin: () => import("@shikijs/langs/kotlin"),
  markdown: () => import("@shikijs/langs/markdown"),
  php: () => import("@shikijs/langs/php"),
  python: () => import("@shikijs/langs/python"),
  ruby: () => import("@shikijs/langs/ruby"),
  rust: () => import("@shikijs/langs/rust"),
  sql: () => import("@shikijs/langs/sql"),
  swift: () => import("@shikijs/langs/swift"),
  toml: () => import("@shikijs/langs/toml"),
  tsx: () => import("@shikijs/langs/tsx"),
  typescript: () => import("@shikijs/langs/typescript"),
  xml: () => import("@shikijs/langs/xml"),
  yaml: () => import("@shikijs/langs/yaml"),
};

/** Kullanıcının serbest yazdığı etiket → kanonik dil adı. */
const LANGUAGE_ALIASES: Record<string, string> = {
  "c++": "cpp",
  cs: "csharp",
  dockerfile: "docker",
  gd: "gdscript",
  golang: "go",
  js: "javascript",
  jsonc: "json",
  kt: "kotlin",
  md: "markdown",
  py: "python",
  rb: "ruby",
  rs: "rust",
  sh: "bash",
  shell: "bash",
  ts: "typescript",
  yml: "yaml",
  zsh: "bash",
};

/** Serbest yazılmış dil etiketini desteklenen bir dile indir. */
export function canonicalLanguage(raw: string): string | null {
  const key = raw.trim().toLocaleLowerCase("en").split(/[\s:,]/)[0];
  if (!key) return null;
  const kanonik = LANGUAGE_ALIASES[key] ?? key;
  return kanonik in LANGUAGE_LOADERS ? kanonik : null;
}

interface CoreHighlighter {
  codeToTokens: (
    code: string,
    options: { lang: string; themes: { light: string; dark: string } },
  ) => { tokens: HighlightedLine[] };
  loadLanguage: (language: unknown) => Promise<void>;
}

let highlighterPromise: Promise<CoreHighlighter> | null = null;
const loadedLanguages = new Set<string>();

/** Çekirdek renklendirici — süreç başına tek örnek, ilk kullanımda kurulur. */
async function getHighlighter(): Promise<CoreHighlighter> {
  if (highlighterPromise === null) {
    highlighterPromise = (async () => {
      const [{ createHighlighterCore }, { createJavaScriptRegexEngine }, light, dark] =
        await Promise.all([
          import("shiki/core"),
          import("shiki/engine/javascript"),
          import("@shikijs/themes/github-light"),
          import("@shikijs/themes/github-dark"),
        ]);
      return (await createHighlighterCore({
        engine: createJavaScriptRegexEngine({ forgiving: true }),
        langs: [],
        themes: [light.default, dark.default],
      })) as unknown as CoreHighlighter;
    })();
  }
  return highlighterPromise;
}

/**
 * Kodu renklendir; dil tanınmıyorsa ya da yükleme düşerse `null` döndür.
 *
 * Hata YUTULMAZ ama çağırana taşınmaz: renklendirme bir SÜStür, kodun kendisi
 * bilgidir. Renklendirme düştüğünde çağıran düz metni çizer, kullanıcı kodu
 * yine görür.
 */
export async function highlight(code: string, language: string): Promise<HighlightedLine[] | null> {
  const canonical = canonicalLanguage(language);
  if (canonical === null) return null;
  try {
    const highlighter = await getHighlighter();
    if (!loadedLanguages.has(canonical)) {
      const grammar = await LANGUAGE_LOADERS[canonical]();
      await highlighter.loadLanguage((grammar as { default: unknown }).default);
      loadedLanguages.add(canonical);
    }
    return highlighter.codeToTokens(code, {
      lang: canonical,
      themes: { light: LIGHT_THEME, dark: DARK_THEME },
    }).tokens;
  } catch {
    return null;
  }
}

/** Testlerin örnek durumunu sıfırlayabilmesi için; üretimde çağrılmaz. */
export function resetHighlighterForTests(): void {
  highlighterPromise = null;
  loadedLanguages.clear();
}

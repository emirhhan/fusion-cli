/** Fusion host'unun temasını Kits'e uygular: adres parametresi ve canlı mesaj. */
export const HOST_THEME_MESSAGE = 'fusion-kits-theme';
const THEMES = ['dark', 'light'] as const;
type Theme = (typeof THEMES)[number];

function isTheme(value: unknown): value is Theme {
  return (
    typeof value === 'string' && (THEMES as readonly string[]).includes(value)
  );
}

interface ThemeRoot {
  dataset: Record<string, string | undefined>;
}

export function applyHostTheme(
  value: unknown,
  root: ThemeRoot = document.documentElement,
): boolean {
  if (!isTheme(value)) return false;
  if (value === 'dark') root.dataset.theme = 'dark';
  else delete root.dataset.theme;
  return true;
}

/** Yalnız gömen pencereden (parent) gelen tema mesajı kabul edilir. */
export function listenHostTheme(
  view: Pick<Window, 'parent' | 'addEventListener' | 'removeEventListener'>,
  root?: ThemeRoot,
): () => void {
  const onMessage = (event: MessageEvent) => {
    if (view.parent === view || event.source !== view.parent) return;
    const data = event.data as { type?: unknown; theme?: unknown } | null;
    if (data?.type === HOST_THEME_MESSAGE) applyHostTheme(data.theme, root);
  };
  view.addEventListener('message', onMessage);
  return () => view.removeEventListener('message', onMessage);
}

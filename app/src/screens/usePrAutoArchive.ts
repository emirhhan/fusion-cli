import { useEffect, useRef, useSyncExternalStore } from "react";

/**
 * Claude Desktop "Auto-archive after PR merge or close" (#443).
 *
 * Ayar açıkken kenar çubuğu, arşivlenmemiş ve şu an çalışmayan sohbetlerin bağlı PR'ını
 * çekirdeğe sorar (`sohbet.pr_durumlari`, `gh pr view --json state`); PR birleşti (`MERGED`) ya da
 * kapandıysa (`CLOSED`) sohbeti arşivler. Çalışan oturum atlanır. Kullanıcı otomatik
 * arşivlenen sohbeti arşivden çıkarırsa aynı sohbet bir daha otomatik arşivlenmez.
 * Varsayılan kapalı; tercih bu bilgisayarda saklanır.
 */
export const AUTO_ARCHIVE_PR_KEY = "fusion.sidebar.auto-archive-pr.v1";
export const AUTO_ARCHIVED_KEY = "fusion.sidebar.pr-auto-archived.v1";
/** İki sorgu arasındaki en kısa süre ve düzenli denetim aralığı (ms). */
export const AUTO_ARCHIVE_MIN_GAP_MS = 60_000;
export const AUTO_ARCHIVE_INTERVAL_MS = 5 * 60_000;
const CLOSED_STATES = new Set(["MERGED", "CLOSED"]);

const listeners = new Set<() => void>();

export function autoArchivePrEnabled(): boolean {
  try {
    return localStorage.getItem(AUTO_ARCHIVE_PR_KEY) === "true";
  } catch {
    return false;
  }
}

export function setAutoArchivePr(enabled: boolean): void {
  try {
    localStorage.setItem(AUTO_ARCHIVE_PR_KEY, enabled ? "true" : "false");
  } catch {
    return;
  }
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function useAutoArchivePr(): boolean {
  return useSyncExternalStore(subscribe, autoArchivePrEnabled, () => false);
}

function readHandled(): string[] {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(AUTO_ARCHIVED_KEY) ?? "[]");
    return Array.isArray(saved) ? saved.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function rememberHandled(keys: string[]): void {
  try {
    localStorage.setItem(AUTO_ARCHIVED_KEY, JSON.stringify([...new Set([...readHandled(), ...keys])]));
  } catch {
    // Depo kapalı: bu pencerede yine arşivlenir; yeniden açılışta tekrar sorulabilir.
  }
}

export interface AutoArchiveCandidate {
  id: string;
  key: string;
  running: boolean;
  archived: boolean;
}

export type PrStateQuery = (ids: string[]) => Promise<Record<string, string>>;

/** Ayar açıksa adayları denetle; kapanmış PR'lı sohbetlerin anahtarlarını `archive`'a ver. */
export function usePrAutoArchive(
  candidates: AutoArchiveCandidate[],
  query: PrStateQuery | undefined,
  archive: (keys: string[]) => void,
): void {
  const enabled = useAutoArchivePr();
  const latest = useRef({ candidates, query, archive });
  latest.current = { candidates, query, archive };
  const lastRun = useRef(0);
  useEffect(() => {
    if (!enabled || !query) return;
    let cancelled = false;
    const check = async (force: boolean) => {
      const now = Date.now();
      if (!force && now - lastRun.current < AUTO_ARCHIVE_MIN_GAP_MS) return;
      lastRun.current = now;
      const current = latest.current;
      const handled = new Set(readHandled());
      const eligible = current.candidates.filter((item) => !item.archived && !item.running && !handled.has(item.key));
      if (!eligible.length || !current.query) return;
      let states: Record<string, string>;
      try {
        states = await current.query(eligible.map((item) => item.id));
      } catch {
        return; // Çekirdek yok ya da `gh` hata verdi: tahminle arşivlenmez.
      }
      if (cancelled) return;
      // Yanıt gelirken tur başlamış olabilir: çalışan oturum yine atlanır.
      const runningNow = new Set(latest.current.candidates.filter((item) => item.running).map((item) => item.id));
      const keys = eligible.filter((item) => CLOSED_STATES.has(states?.[item.id] ?? "") && !runningNow.has(item.id)).map((item) => item.key);
      if (!keys.length) return;
      rememberHandled(keys);
      latest.current.archive(keys);
    };
    void check(true);
    const onFocus = () => { void check(false); };
    window.addEventListener("focus", onFocus);
    const timer = window.setInterval(() => { void check(true); }, AUTO_ARCHIVE_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", onFocus);
      window.clearInterval(timer);
    };
  }, [enabled, query]);
}

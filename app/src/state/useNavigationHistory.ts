import { useCallback, useState } from "react";

interface NavigationHistoryState<T> {
  entries: T[];
  index: number;
}

interface NavigationHistory<T> {
  back: () => void;
  canGoBack: boolean;
  canGoForward: boolean;
  current: T;
  forward: () => void;
  /** Yeni bir sayfaya geçer; geri yığınına ekler ve ileri yığınını temizler. */
  push: (value: T) => void;
}

/**
 * Tarayıcı geri/ileri geçmişine benzer, generic bir gezinme yığını.
 *
 * Üst çubuktaki geri/ileri düğmeleri için kullanılır: sayfalar arasında
 * (sohbet, ayarlar, beceriler…) `push` ile geçilir, `back`/`forward` yığını
 * gezer. Aynı sayfaya art arda `push` çağrısı yeni girdi eklemez — kullanıcı
 * bir sayfada kalırken her tıklama geçmişi şişirmesin diye.
 */
export function useNavigationHistory<T>(initial: T): NavigationHistory<T> {
  const [state, setState] = useState<NavigationHistoryState<T>>({ entries: [initial], index: 0 });

  const push = useCallback((value: T) => {
    setState((current) => {
      if (current.entries[current.index] === value) return current;
      const truncated = current.entries.slice(0, current.index + 1);
      return { entries: [...truncated, value], index: truncated.length };
    });
  }, []);

  const back = useCallback(() => {
    setState((current) => (current.index > 0 ? { ...current, index: current.index - 1 } : current));
  }, []);

  const forward = useCallback(() => {
    setState((current) =>
      current.index < current.entries.length - 1 ? { ...current, index: current.index + 1 } : current,
    );
  }, []);

  return {
    back,
    canGoBack: state.index > 0,
    canGoForward: state.index < state.entries.length - 1,
    current: state.entries[state.index],
    forward,
    push,
  };
}

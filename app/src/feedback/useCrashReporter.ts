import { useCallback, useEffect, useState } from "react";

export interface CrashInfo {
  mesaj: string;
  ayrinti: string;
}

/**
 * Tarayıcının kendisinin ürettiği, uygulamayı bozmayan gürültü. Bunlar için
 * kullanıcıya "Fusion bir hatayla karşılaştı" demek yanlış alarm olur.
 */
const ZARARSIZ = [/ResizeObserver loop/i];

function describe(reason: unknown): CrashInfo {
  if (reason instanceof Error) {
    return { mesaj: reason.message || reason.name, ayrinti: reason.stack ?? `${reason.name}: ${reason.message}` };
  }
  const metin = typeof reason === "string" ? reason : JSON.stringify(reason) ?? String(reason);
  return { mesaj: metin, ayrinti: metin };
}

/**
 * Arayüzde yakalanmamış hataları dinler (Apple'ın "rapor gönder" akışı gibi).
 * Hata olduğunda son hatayı döndürür; arayüz kullanıcıya bildirmeyi önerir.
 * Hiçbir şey kendiliğinden gönderilmez.
 */
export function useCrashReporter(): [CrashInfo | null, () => void] {
  const [crash, setCrash] = useState<CrashInfo | null>(null);

  useEffect(() => {
    const kaydet = (reason: unknown, fallback: string) => {
      const info = describe(reason ?? fallback);
      if (ZARARSIZ.some((pattern) => pattern.test(info.mesaj))) return;
      // İlk hata korunur: zincirleme hatalar asıl nedeni ezmesin.
      setCrash((current) => current ?? info);
    };
    const onError = (event: ErrorEvent) => kaydet(event.error, event.message);
    const onRejection = (event: PromiseRejectionEvent) => kaydet(event.reason, "İşlenmemiş Promise reddi");
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onRejection);
    };
  }, []);

  const temizle = useCallback(() => setCrash(null), []);
  return [crash, temizle];
}

import { useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";

/** Rust'ın nabız zaman aşımı (10 sn) bunun çok üstündedir; arada kayıp nabız onu tetiklemez. */
export const NABIZ_ARALIGI_MS = 1000;

function nabizGonder(): Promise<unknown> {
  return invoke("kapatma_nabzi");
}

/**
 * Kapatma sorusu açıkken (`aktif`) Rust'a arayüzün canlı olduğunu bildirir (R2-14).
 *
 * Nabız kesilirse (donmuş/çökmüş web görünümü) Rust bir süre sonra kapanışı onaysız sürdürür;
 * aksi halde uygulama yalnız süreç öldürülerek kapanabilirdi. Gönderim hatası yutulur: nabız
 * ulaşmazsa zaten amaçlanan sonuç budur.
 */
export function useKapatmaNabzi(aktif: boolean, gonder: () => Promise<unknown> = nabizGonder): void {
  useEffect(() => {
    if (!aktif) return;
    const yolla = () => { void gonder().catch(() => undefined); };
    yolla();
    const zamanlayici = setInterval(yolla, NABIZ_ARALIGI_MS);
    return () => clearInterval(zamanlayici);
  }, [aktif, gonder]);
}

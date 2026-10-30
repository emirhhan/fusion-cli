import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { kabukVar } from "../voice/bridge";

/** Rust'ta kayıtlı özel şema (bkz. `onizleme.rs`). */
const ONIZLEME_SEMASI = "fusion-preview";

/**
 * HTML önizlemesini ana pencereden AYRI kökenli bir adresten sunar (U4-47).
 *
 * `srcdoc` iframe'i ana pencerenin CSP'sini (`script-src 'self'`) miras alır; paketli uygulamada
 * önizlenen sayfanın satır içi betikleri çalışmazdı. İçerik Rust'a bırakılır ve `fusion-preview://`
 * şemasından kendi CSP başlığıyla sunulur; ana pencerenin CSP'si gevşemez. `null` dönerse (tarayıcı,
 * test ya da Rust reddetti) çağıran eski `srcdoc` yoluna düşer.
 */
export async function ayriKokenliOnizlemeAdresi(html: string): Promise<string | null> {
  if (!kabukVar()) return null;
  try {
    const anahtar = await invoke<string>("onizleme_ayarla", { icerik: html });
    return convertFileSrc(anahtar, ONIZLEME_SEMASI);
  } catch {
    return null;
  }
}

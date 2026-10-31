import deniz from "./avatars/deniz.svg";
import elif from "./avatars/elif.svg";
import zeynep from "./avatars/zeynep.svg";
import kerem from "./avatars/kerem.svg";
import emre from "./avatars/emre.svg";
import can from "./avatars/can.svg";
import arda from "./avatars/arda.svg";

/**
 * Fusion'a ait hazır avatarlar (Notionists, CC0 — bkz. `avatars/LISANS.md`).
 *
 * Hesapta `avatar` alanı tek metindir; hazır avatar `fusion:<kimlik>` olarak saklanır.
 * Böylece şema değişmez: emoji (eski), dosya yolu (yüklenen görsel) ve hazır avatar
 * aynı alanda ayırt edilir. SVG'ler paketle gelir; çalışırken ağdan bir şey inmez.
 */

export interface FusionAvatar {
  id: string;
  ad: string;
  src: string;
}

export const FUSION_AVATAR_ONEKI = "fusion:";

export const FUSION_AVATARLARI: readonly FusionAvatar[] = [
  { id: "deniz", ad: "Deniz", src: deniz },
  { id: "elif", ad: "Elif", src: elif },
  { id: "zeynep", ad: "Zeynep", src: zeynep },
  { id: "kerem", ad: "Kerem", src: kerem },
  { id: "emre", ad: "Emre", src: emre },
  { id: "can", ad: "Can", src: can },
  { id: "arda", ad: "Arda", src: arda },
];

/** Eski emoji seçimi olan hesapta gösterilen avatar. */
export const VARSAYILAN_FUSION_AVATARI: FusionAvatar = FUSION_AVATARLARI[0];

export function fusionAvatarDegeri(avatar: FusionAvatar): string {
  return `${FUSION_AVATAR_ONEKI}${avatar.id}`;
}

/** `fusion:<kimlik>` değerini çözer; tanınmayan kimlik varsayılan avatara düşer. */
export function fusionAvatariBul(deger: string): FusionAvatar | null {
  if (!deger.startsWith(FUSION_AVATAR_ONEKI)) return null;
  const kimlik = deger.slice(FUSION_AVATAR_ONEKI.length);
  return FUSION_AVATARLARI.find((avatar) => avatar.id === kimlik) ?? VARSAYILAN_FUSION_AVATARI;
}

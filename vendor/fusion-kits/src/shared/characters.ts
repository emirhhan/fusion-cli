/** Kalıcı Kit kimlikleri; yeni görseller sürümlü /dots/v3 adresinden gelir. */
export const KIT_CHARACTERS = [
  { id: 'blue', label: 'Mavi' },
  { id: 'mint', label: 'Camgöbeği' },
  { id: 'orange', label: 'Kobalt' },
  { id: 'purple', label: 'Mor' },
  { id: 'green', label: 'Peri mavisi' },
  { id: 'pink', label: 'Lavanta' },
  { id: 'yellow', label: 'Gümüş' },
  { id: 'red', label: 'Gece mavisi' },
] as const;
export type KitCharacter = (typeof KIT_CHARACTERS)[number]['id'];
const ids: readonly string[] = KIT_CHARACTERS.map((item) => item.id);
export function isKitCharacter(value: unknown): value is KitCharacter {
  return typeof value === 'string' && ids.includes(value);
}
/** Eski Kit'ler için kimlikten kararlı karakter (göç öncesi görünümle aynı). */
export function characterFromIdentity(identity?: string): KitCharacter {
  const legacy = ['blue', 'mint', 'orange', 'purple'] as const;
  if (!identity) return legacy[0];
  let hash = 0;
  for (const letter of identity)
    hash = (hash * 31 + letter.charCodeAt(0)) >>> 0;
  return legacy[hash % legacy.length];
}
export function resolveCharacter(
  character?: string | null,
  identity?: string,
): KitCharacter {
  return isKitCharacter(character)
    ? character
    : characterFromIdentity(identity);
}
/** Yeni Kit'e henüz kullanılmayan ilk karakter; hepsi kullanıldıysa ilki. */
export function firstUnusedCharacter(
  used: readonly (string | null | undefined)[],
) {
  return (
    KIT_CHARACTERS.find((item) => !used.includes(item.id))?.id ??
    KIT_CHARACTERS[0].id
  );
}

/** Geçersiz kayıt bir dosya yoluna dönüşmez; mevcut kimlik çözümlemesi kullanılır. */
export function characterImage(
  character?: string | null,
  identity?: string,
): string {
  return `/dots/v3/${resolveCharacter(character, identity)}.png`;
}

/**
 * Olay yükünü kullanıcıya gösterilecek bir ADIMA çevirir.
 *
 * Ham JSON asla gösterilmez: kullanıcı ne olduğunu okumak ister, veri yapısını
 * değil. Karşılığı olmayan olaylar `null` döner ve akışta hiç görünmez.
 *
 * Her adım kısa bir başlık ve ONU AÇAN bir ayrıntı taşır: hangi model
 * düşünüyor, hangi araç hangi dosyaya/adrese gitti. Eskiden yalnız başlık
 * vardı ve arka arkaya iki "model düşünüyor…" satırı, ikisinin farklı roller
 * olduğunu gizliyordu.
 */

export interface OlayAdimi {
  /** Kısa başlık: "düşünüyor", "dosya yazdı"… */
  metin: string;
  /** Başlığı açan tek satır: rol, model, dosya yolu. */
  ayrinti?: string;
  /** Varsa gidilen adres; arayüz bunu kaynak olarak gösterir. */
  kaynak?: string;
  /** Turun sonucu gibi kendi başına duran adımlar akışta ayrı satır olur. */
  sonuc?: boolean;
}

/** Araç argümanlarından okunabilir tek satır çıkar. */
function aracAyrintisi(args: unknown): { ayrinti?: string; kaynak?: string } {
  if (!args || typeof args !== "object") return {};
  const row = args as Record<string, unknown>;
  const url = typeof row.url === "string" ? row.url : undefined;
  const path = typeof row.path === "string" ? row.path : undefined;
  const command = typeof row.command === "string" ? row.command : undefined;
  const query = typeof row.query === "string" ? row.query : undefined;
  return { ayrinti: url ?? path ?? command ?? query, kaynak: url };
}

export function olayAdimi(veri: Record<string, unknown>): OlayAdimi | null {
  const olay = String(veri.olay ?? "");
  const ad = typeof veri.name === "string" ? veri.name : "";
  switch (olay) {
    case "ToolExecuted": {
      const { ayrinti, kaynak } = aracAyrintisi(veri.args);
      return { metin: `araç çalıştı: ${ad}`, ayrinti, kaynak };
    }
    case "ModelCallStarted": {
      // Arka plan çağrıları (hakem, sentez, öz-denetim) kullanıcının ilerleme
      // akışına GİRMEZ: onlar muhasebe içindir, ekranı kalabalıklaştırırlar.
      if (veri.background === true) return null;
      const rol = typeof veri.role === "string" ? veri.role : "";
      const model = typeof veri.model === "string" ? veri.model : "";
      return {
        metin: "düşünüyor",
        ayrinti: [rol, model].filter(Boolean).join(" · ") || undefined,
      };
    }
    case "ModelFallbackActivated":
      return {
        metin: "yedek modele geçti",
        ayrinti: `${String(veri.requested_model ?? "")} → ${String(veri.fallback_model ?? "")}`,
      };
    case "CapabilityActivated":
      return {
        metin: `${String(veri.name ?? "uzmanlık")} seçildi`,
        ayrinti: `kaynak: ${String(veri.source ?? "fusion")}`,
      };
    case "FilesChanged": {
      const paths = veri.paths;
      if (!Array.isArray(paths) || !paths.every((path) => typeof path === "string")) return null;
      return { metin: "dosyalar değişti", ayrinti: paths.join(", ") };
    }
    case "TurnOutcome": {
      const durum = String(veri.status ?? "");
      if (durum === "completed") return { metin: "görev tamamlandı", sonuc: true };
      if (durum === "partial") return { metin: "görev kısmi kaldı", sonuc: true };
      return { metin: "görev başarısız", sonuc: true };
    }
    default:
      return null;
  }
}

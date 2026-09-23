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

export type OlaySonucu = "completed" | "partial" | "failed";

export interface OlayAdimi {
  /** Kısa başlık: "düşünüyor", "dosya yazdı"… */
  metin: string;
  /** Başlığı açan tek satır: rol, model, dosya yolu. */
  ayrinti?: string;
  /** Varsa gidilen adres; arayüz bunu kaynak olarak gösterir. */
  kaynak?: string;
  /** Turun sonucu gibi kendi başına duran adımlar akışta ayrı satır olur. */
  sonuc?: OlaySonucu;
  /** Değiştirici dosya aracı BAŞARIYLA çalıştıysa ürettiği unified diff. */
  diff?: string;
  /** `diff` varsa değişen dosyanın yolu. */
  yol?: string;
  /** Adım bir ALT AJAN turuna ait mi? Arayüz onu ayrı işaretler.
   *
   *  CLI'de bu ayrım `┌ alt-ajan` başlığıyla zaten vardı; masaüstünde alt
   *  ajanın adımları ana turun adımlarına karışıyordu ve kullanıcı hangi işin
   *  kim tarafından yapıldığını göremiyordu. */
  altAjan?: boolean;
  /** Modelin düşünme metni (varsa). Yalnız "adımları göster" açıkken çizilir.
   *
   *  Veri zaten akışta taşınıyordu (`ModelCallFinished.result.reasoning`) ama
   *  masaüstünde hiç okunmuyordu; CLI'de `--show-thinking` ile görünüyordu. */
  dusunme?: string;
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

/**
 * Araç sonucunun başlığı. Reddedilen ya da kapsam dışı kalan çağrı "çalıştı"
 * görünürse kullanıcı dosyanın yazıldığını sanır; ölçüldü: kurtarma turundaki
 * `write_file` engellenmişti ama akış "araç çalıştı" diyordu.
 */
const ARAC_SONUCU: Record<string, string> = {
  ok: "araç çalıştı",
  failed: "araç başarısız",
  denied: "araç reddedildi",
  blocked: "araç engellendi",
};

export function olayAdimi(veri: Record<string, unknown>): OlayAdimi | null {
  const olay = String(veri.olay ?? "");
  const ad = typeof veri.name === "string" ? veri.name : "";
  switch (olay) {
    case "ToolExecuted": {
      const { ayrinti, kaynak } = aracAyrintisi(veri.args);
      const baslik = ARAC_SONUCU[String(veri.outcome ?? "ok")] ?? ARAC_SONUCU.ok;
      // Diff YALNIZ başarılı çağrıda taşınır. Engellenen ya da düşen bir
      // yazmanın diff'ini göstermek, yapılmamış bir değişikliği yapılmış gibi
      // sunardı — bu, `ARAC_SONUCU` ayrımının zaten kapattığı tuzağın aynısı.
      const diff = veri.outcome === "ok" && typeof veri.diff === "string" && veri.diff
        ? veri.diff
        : undefined;
      return { metin: `${baslik}: ${ad}`, ayrinti, kaynak, diff, yol: diff ? ayrinti : undefined };
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
    case "ModelCallFinished": {
      // Arka plan çağrıları akışa girmez (`ModelCallStarted` ile aynı gerekçe).
      if (veri.background === true) return null;
      const sonuc = veri.result as { reasoning?: unknown } | undefined;
      const dusunme = typeof sonuc?.reasoning === "string" ? sonuc.reasoning.trim() : "";
      // Düşünme YOKSA adım da yok: her model çağrısı için boş bir satır açmak
      // akışı ikiye katlar ("düşünüyor" zaten `ModelCallStarted`'da basılıyor).
      if (!dusunme) return null;
      return { metin: "düşündü", dusunme };
    }
    case "SubAgentStarted": {
      const gorev = typeof veri.task === "string" ? veri.task : "";
      return { metin: "alt ajan başladı", ayrinti: gorev || undefined, altAjan: true };
    }
    case "SubAgentFinished": {
      const cagri = typeof veri.tool_calls === "number" ? veri.tool_calls : null;
      return {
        metin: "alt ajan bitti",
        ayrinti: cagri === null ? undefined : `${cagri} araç çağrısı`,
        altAjan: true,
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
    case "ExecutionRouteSelected":
      return {
        metin: String(veri.route ?? "") === "workflow" ? "planlı yürütme seçildi" : "hızlı yürütme seçildi",
        ayrinti: Array.isArray(veri.reasons) ? veri.reasons.join(" · ") : undefined,
      };
    case "ExecutionPromoted":
      return {
        metin: "görev planlı yürütmeye yükseltildi",
        ayrinti: Array.isArray(veri.reasons) ? veri.reasons.join(" · ") : undefined,
      };
    case "ExecutionPlanCreated":
      return {
        metin: `plan hazır: ${Number(veri.total_steps ?? 0)} adım`,
        ayrinti: typeof veri.plan_id === "string" ? veri.plan_id : undefined,
      };
    case "ExecutionStepStarted":
      return {
        metin: `adım ${Number(veri.index ?? 0)}/${Number(veri.total_steps ?? 0)} başladı`,
        ayrinti: typeof veri.goal === "string" ? veri.goal : undefined,
      };
    case "ExecutionStepVerified": {
      const ok = veri.ok === true;
      const details = ok ? veri.evidence : veri.findings;
      return {
        metin: `${String(veri.step_id ?? "adım")} ${ok ? "doğrulandı" : "doğrulanamadı"}`,
        ayrinti: Array.isArray(details) ? details.join(" · ") : undefined,
      };
    }
    case "ExecutionRetryScheduled":
      return {
        metin: `kurtarma: ${String(veri.action ?? "retry")}`,
        ayrinti: typeof veri.reason === "string" ? veri.reason : undefined,
      };
    case "ExecutionCheckpointSaved":
      return { metin: `checkpoint: ${Number(veri.completed_steps ?? 0)} adım tamam` };
    case "ExecutionPaused":
      return {
        metin: "workflow duraklatıldı",
        ayrinti: typeof veri.reason === "string" ? veri.reason : undefined,
      };
    case "ExecutionCompleted":
      // Kabul kapısının KANITLAYAMADIĞI şey de görünmeli; "tamamlandı" tek
      // başına işin doğrulandığı izlenimi verir.
      return {
        metin: `plan tamamlandı: ${Number(veri.total_steps ?? 0)} adım`,
        ayrinti: Array.isArray(veri.warnings) && veri.warnings.length
          ? veri.warnings.join(" · ")
          : undefined,
      };
    case "FilesChanged": {
      const paths = veri.paths;
      if (!Array.isArray(paths) || !paths.every((path) => typeof path === "string")) return null;
      return { metin: "dosyalar değişti", ayrinti: paths.join(", ") };
    }
    case "TurnOutcome": {
      const durum = String(veri.status ?? "");
      if (durum === "completed") return { metin: "görev tamamlandı", sonuc: "completed" };
      if (durum === "partial") return { metin: "görev kısmi kaldı", sonuc: "partial" };
      return { metin: "görev başarısız", sonuc: "failed" };
    }
    default:
      return null;
  }
}

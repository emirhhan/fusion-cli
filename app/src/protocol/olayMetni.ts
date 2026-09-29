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
  /** Adım bir araç çağrısıysa aracın adı; başlayan ve biten olay bununla eşleşir. */
  arac?: string;
  /** Araç başladı ama henüz bitmedi (`ToolStarted`). */
  basladi?: boolean;
  /** Araç bittiyse sonucu: ok | failed | denied | blocked. */
  durum?: string;
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

/**
 * Uzun MUTLAK yolu son iki parçaya kısaltır.
 *
 * Ölçüldü: `/Users/kullanici/Desktop/ornek-proje/lib/x.ts` gibi bir yol adım
 * satırının tamamını kaplıyor, satır kayıyor/kırpılıyordu. Kullanıcı zaten
 * hangi PROJEDE çalıştığını bilir; onun için anlamlı olan son parçalardır
 * ("lib/x.ts"). Göreli/kısa yollara dokunulmaz.
 */
function kisaYol(yol: string): string {
  const mutlakMi = yol.startsWith("/") || /^[a-zA-Z]:[\\/]/.test(yol);
  if (!mutlakMi) return yol;
  const parcalar = yol.split(/[\\/]+/).filter(Boolean);
  return parcalar.length > 2 ? parcalar.slice(-2).join("/") : yol;
}

/** Araç argümanlarından okunabilir tek satır çıkar. */
function aracAyrintisi(args: unknown): { ayrinti?: string; kaynak?: string } {
  if (!args || typeof args !== "object") return {};
  const row = args as Record<string, unknown>;
  const url = typeof row.url === "string" ? row.url : undefined;
  const path = typeof row.path === "string" ? row.path : undefined;
  const command = typeof row.command === "string" ? row.command : undefined;
  const query = typeof row.query === "string" ? row.query : undefined;
  return { ayrinti: url ?? (path ? kisaYol(path) : undefined) ?? command ?? query, kaynak: url };
}

/** Alıntılanan metnin üst sınırı; durum satırı tek satırda kalmalı. */
const TIRNAK_SINIRI = 60;

function metinAl(args: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const value = args[key];
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return undefined;
}

function tirnakla(value: string | undefined): string {
  if (!value) return "";
  const kirpik = value.length <= TIRNAK_SINIRI ? value : `${value.slice(0, TIRNAK_SINIRI - 1)}…`;
  return `'${kirpik}'`;
}

function sunucuAdi(url: string | undefined): string {
  if (!url) return "sayfa";
  try {
    return new URL(url.includes("://") ? url : `https://${url}`).host || url;
  } catch {
    return url;
  }
}

function yolMetni(args: Record<string, unknown>): string {
  const yol = metinAl(args, "path", "yol");
  return yol ? kisaYol(yol) : "dosya";
}

function tarayiciGenel(fiil: string): (args: Record<string, unknown>) => string {
  return () => `tarayıcı ile ${fiil}`;
}

function masaustuGenel(fiil: string): (args: Record<string, unknown>) => string {
  return () => `masaüstünde ${fiil}`;
}

const ARAC_VARSAYILAN_METNI: Record<string, (args: Record<string, unknown>) => string> = {
  read_file: (args) => `${yolMetni(args)} okunuyor`,
  write_file: (args) => `${yolMetni(args)} yazılıyor`,
  edit_file: (args) => `${yolMetni(args)} düzenleniyor`,
  multi_edit: (args) => `${yolMetni(args)} düzenleniyor`,
  list_dir: (args) => {
    const yol = metinAl(args, "path", "yol");
    return yol ? `${kisaYol(yol)} listeleniyor` : "dizin listeleniyor";
  },
  search_code: (args) => {
    const sorgu = metinAl(args, "query", "pattern", "sorgu");
    return sorgu ? `${tirnakla(sorgu)} kod içinde aranıyor` : "kod içinde arama yapılıyor";
  },
  glob: (args) => {
    const desen = metinAl(args, "pattern", "desen");
    return desen ? `${tirnakla(desen)} desenine uyan dosyalar bulunuyor` : "dosyalar bulunuyor";
  },
  git: (args) => {
    const altKomut = metinAl(args, "subcommand", "komut");
    return altKomut ? `git ${altKomut} çalıştırılıyor` : "git komutu çalıştırılıyor";
  },
  run_shell: (args) => {
    const komut = metinAl(args, "command", "komut");
    return komut ? `kabuk komutu ${tirnakla(komut)} çalıştırılıyor` : "kabuk komutu çalıştırılıyor";
  },
  todo_write: () => "görev listesi güncelleniyor",
  web_search: (args) => {
    const sorgu = metinAl(args, "query", "sorgu");
    return sorgu ? `${tirnakla(sorgu)} web'de aranıyor` : "web'de arama yapılıyor";
  },
  web_fetch: (args) => `${sunucuAdi(metinAl(args, "url"))} getiriliyor`,
  download_file: (args) => `${sunucuAdi(metinAl(args, "url"))} indiriliyor`,
  extract_archive: (args) => `${yolMetni(args)} açılıyor`,
  scaffold_web: () => "web iskeleti oluşturuluyor",
  chrome_navigate: (args) => `chrome ile ${sunucuAdi(metinAl(args, "url"))} açılıyor`,
  chrome_click: () => "chrome ile bir öğeye tıklanıyor",
  chrome_type: (args) => {
    const metin = metinAl(args, "text");
    return metin ? `chrome ile ${tirnakla(metin)} yazılıyor` : "chrome ile yazı yazılıyor";
  },
  chrome_page: () => "chrome ile sayfa okunuyor",
  chrome_action: (args) => {
    const eylem = args.action;
    if (eylem === "scroll") return "chrome ile sayfa kaydırılıyor";
    if (eylem === "wait") return "chrome ile bekleniyor";
    if (eylem === "key") return "chrome ile tuşa basılıyor";
    if (eylem === "screenshot") return "chrome ile ekran görüntüsü alınıyor";
    return "chrome ile sayfa etkileşimi yapılıyor";
  },
  browser_open: (args) => {
    const url = metinAl(args, "url");
    return url ? `tarayıcı ile ${sunucuAdi(url)} açılıyor` : "tarayıcı açılıyor";
  },
  browser_read: tarayiciGenel("sayfa okunuyor"),
  browser_tabs_list: tarayiciGenel("sekmeler listeleniyor"),
  browser_tab_select: tarayiciGenel("sekme seçiliyor"),
  browser_tab_open: tarayiciGenel("yeni sekme açılıyor"),
  browser_type: tarayiciGenel("yazı yazılıyor"),
  browser_click: tarayiciGenel("bir öğeye tıklanıyor"),
  browser_screenshot: tarayiciGenel("ekran görüntüsü alınıyor"),
  browser_mirror: tarayiciGenel("ekran yansıtılıyor"),
  browser_close: tarayiciGenel("tarayıcı kapatılıyor"),
  desktop_windows: masaustuGenel("pencereler listeleniyor"),
  desktop_window_focus: masaustuGenel("pencereye geçiliyor"),
  desktop_accessibility: masaustuGenel("erişilebilirlik ağacı okunuyor"),
  desktop_apps: masaustuGenel("uygulamalar listeleniyor"),
  desktop_open: (args) => {
    const hedef = metinAl(args, "path", "uygulama", "app");
    return hedef ? `masaüstünde ${hedef} açılıyor` : "masaüstünde uygulama açılıyor";
  },
  desktop_screenshot: masaustuGenel("ekran görüntüsü alınıyor"),
  desktop_click: masaustuGenel("bir öğeye tıklanıyor"),
  desktop_type: masaustuGenel("yazı yazılıyor"),
  desktop_key: masaustuGenel("tuşa basılıyor"),
  desktop_scroll: masaustuGenel("sayfa kaydırılıyor"),
};

/**
 * Bitmiş bir araç çağrısı için insan-okunur varsayılan metin.
 *
 * `ToolExecuted` normalde `adimiEkle` (bkz. `olayAkisi.ts`) ile kendisini AÇAN
 * `ToolStarted` adımının metnini devralır. Ama araya giren bir blok sınırı ya
 * da kayıp olay yüzünden eşleşme kurulamazsa (ölçüldü: "araç çalıştı: glob"
 * gibi ham, anlamsız bir satır kalıyordu) buraya düşülür. Kalıplar bilinçli
 * olarak çekirdeğin `appserver/tool_progress.py::_METINLER` sözlüğüyle AYNI
 * cümleleri üretir — kullanıcı Başladı/Bitti arasında farklı bir ifadeyle
 * karşılaşmasın diye. Çekirdek değişirse bu eşleme de güncellenmelidir;
 * ikinci bir üretim yolu DEĞİL, çekirdeğin TEK kaynağının burada zorunlu bir
 * yedeğidir (ağ/protokol kesintisinde bile arayüz anlamlı kalmalı).
 */
export function aracVarsayilanMetni(ad: string, args: unknown): string {
  const row = args && typeof args === "object" ? (args as Record<string, unknown>) : {};
  const uretici = ARAC_VARSAYILAN_METNI[ad];
  if (uretici) return uretici(row);
  const okunabilirAd = ad.replace(/_/g, " ").trim() || "araç";
  return `${okunabilirAd} çalıştırılıyor`;
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
    case "ToolStarted": {
      // Araç henüz BİTMEDİ; yalnız çalışmaya başladı (onay gerekiyorsa
      // ondan SONRA — bkz. `engines/agent/loop.py::_execute`). Cümle
      // TEK KAYNAKTAN (çekirdek `appserver/tool_progress.py`) gelir,
      // arayüz kendi kalıbını uydurmaz; burada yalnız `veri.metin` basılır.
      // Ardından gelecek `ToolExecuted` aynı bloğun son adımı olarak bu
      // satırın yerini alır — "Düşünüyor…" göstergesinin yaptığı gibi.
      const metin = typeof veri.metin === "string" && veri.metin ? veri.metin : `${ad} çalıştırılıyor`;
      const { kaynak } = aracAyrintisi(veri.args);
      return { metin, kaynak, arac: ad, basladi: true };
    }
    case "ToolExecuted": {
      const { ayrinti, kaynak } = aracAyrintisi(veri.args);
      const durumAdi = String(veri.outcome ?? "ok");
      // Diff YALNIZ başarılı çağrıda taşınır. Engellenen ya da düşen bir
      // yazmanın diff'ini göstermek, yapılmamış bir değişikliği yapılmış gibi
      // sunardı — bu, `ARAC_SONUCU` ayrımının zaten kapattığı tuzağın aynısı.
      const diff = veri.outcome === "ok" && typeof veri.diff === "string" && veri.diff
        ? veri.diff
        : undefined;
      // Dosya açma (`onOpenFile`) TAM yola muhtaçtır; `ayrinti` satırda
      // görünsün diye KISALTILMIŞ olabilir (bkz. `kisaYol`). Bu yüzden `yol`
      // ayrıntıdan değil, argümanın HAM `path`inden alınır.
      const rawArgs = veri.args && typeof veri.args === "object" ? (veri.args as Record<string, unknown>) : {};
      const hamYol = metinAl(rawArgs, "path", "yol");
      // "ok" dışındaki sonuçlar (reddedildi/engellendi/başarısız) zaten kendi
      // başlığıyla açık; yalnız "ok" durumunda ham "araç çalıştı: X" yerine
      // insan-okunur varsayılan metin üretilir (bkz. `aracVarsayilanMetni`).
      const metin = durumAdi === "ok"
        ? aracVarsayilanMetni(ad, veri.args)
        : `${ARAC_SONUCU[durumAdi] ?? ARAC_SONUCU.ok}: ${ad}`;
      return {
        metin, ayrinti, kaynak, diff, yol: diff ? (hamYol ?? ayrinti) : undefined,
        arac: ad, durum: durumAdi,
      };
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
    case "ModelFallbackActivated": {
      const gecis = `${String(veri.requested_model ?? "")} → ${String(veri.fallback_model ?? "")}`;
      const neden = String(veri.reason ?? "");
      // Seçilen web oturumu insan doğrulaması istediği için yedeğe geçildiyse
      // sebep saklanmaz: arayüz bunu görüp "Giriş penceresini aç" kartını açar.
      return {
        metin: "yedek modele geçti",
        ayrinti: neden.includes("insan doğrulaması") ? `${gecis} · ${neden}` : gecis,
      };
    }
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
    case "TeacherTaskClassified":
      return {
        metin: veri.size === "orta-buyuk" ? "orta-büyük görev belirlendi" : "basit görev belirlendi",
        ayrinti: Array.isArray(veri.reasons) ? veri.reasons.join(" · ") : undefined,
      };
    case "TeacherPlanPrepared":
      return {
        metin: veri.structured === true ? "öğretmenden plan alındı" : "öğretmen plan notu alındı",
        ayrinti: veri.structured === true ? `${Number(veri.steps ?? 0)} adım` : undefined,
      };
    case "TeacherLimitationFound":
      return {
        metin: `${String(veri.topic ?? "İş")} yapılamıyor`,
        ayrinti: `${String(veri.reason ?? "")}. Alternatif: ${String(veri.alternative ?? "")}`,
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

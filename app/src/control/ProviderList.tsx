import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ProviderLogo, type ProviderId } from "../brand/ProviderLogo";
import type { ProtocolClient } from "../protocol/client";
import "./ProviderList.css";

/**
 * Sağlayıcı listesi.
 *
 * TEK ve KISA liste: her satırda yalnız ad ve bağlı olup olmadığı yazar.
 * Ayrıntı satıra tıklayınca açılır ve TÜRE GÖRE değişir — web sağlayıcısında
 * oturum açma, anahtarlı sağlayıcıda anahtar alanı. Eskiden her sağlayıcı için
 * ekranda açık duran uzun anahtar kutuları vardı; web sağlayıcıları anahtar
 * kullanmadığı için bu hem yanlış hem yer kaplıyordu.
 */

interface ProviderRow {
  ad: string;
  bagli: boolean;
  eylem: "oturum" | "anahtar";
  hesap?: string;
  id: string;
  ortam?: string;
  /** Tarayıcı profili var mı? Tek başına "bağlı" demek DEĞİLDİR. */
  profil_var?: boolean;
  tur: "web" | "anahtar";
  /** Taklit araç ölçümü geçildi mi — geçmediyse model DOSYA YAZAMAZ. */
  olcum_gecti?: boolean;
  /** Tur tarayıcısının pencere kipi (yalnız web sağlayıcıları). */
  pencere_kipi?: PencereKipi;
  /** Pencereyle ilgili son uyarı — ör. macOS gizleme izni verilmemiş. */
  pencere_uyarisi?: string | null;
  secili_model?: string;
}

type PencereKipi = "visible" | "headless" | "hidden";

/** Kiplerin kullanıcıya görünen adları; gateway panelindeki seçimle aynı. */
const PENCERE_KIPLERI: Record<PencereKipi, string> = {
  visible: "Görünür",
  headless: "Görünmez",
  hidden: "Gizli",
};

const YOKLAMA_MS = 1500;
const GIRIS_SURESI_MS = 15 * 60 * 1000;

export function ProviderList({ client, initialProviderId, onChanged = () => undefined, onDraftChange }: {
  client: ProtocolClient;
  initialProviderId?: string;
  onChanged?: () => void;
  onDraftChange?: (dirty: boolean) => void;
}) {
  const [rows, setRows] = useState<ProviderRow[]>([]);
  const [open, setOpen] = useState<string | null>(initialProviderId ?? null);
  const [query, setQuery] = useState("");
  const [secret, setSecret] = useState("");
  /** Kasada kayıtlı değer; göz düğmesiyle görünür, kaydedince silinmez. */
  const [stored, setStored] = useState("");
  const [reveal, setReveal] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const dirty = secret.trim().length > 0 && secret !== stored;
  useEffect(() => { onDraftChange?.(dirty); }, [dirty, onDraftChange]);
  const [notice, setNotice] = useState<string | null>(null);
  const [modelChoices, setModelChoices] = useState<Record<string, string[]>>({});
  const [modelLoading, setModelLoading] = useState<string | null>(null);
  const [modelError, setModelError] = useState<string | null>(null);
  const timers = useRef<number[]>([]);
  const run = async (operation: () => Promise<void>) => {
    try {
      await operation();
    } catch {
      setBusy(null);
      setNotice("İşlem tamamlanamadı. Bağlantını kontrol edip tekrar dene.");
    }
  };

  const verifyKey = async (row: ProviderRow) => {
    setBusy(row.id);
    setNotice("API anahtarı sınanıyor…");
    const result = await client.request("kontrol.anahtar_dogrula", { saglayici: row.id });
    setNotice(String(result.metin ?? (result.ok ? "API anahtarı doğrulandı." : "Anahtar sınaması geçmedi.")));
    setBusy(null);
  };

  const load = useCallback(async () => {
    try {
      const veri = (await client.request("saglayici.katalog", {})) as {
        ok?: boolean;
        saglayicilar?: ProviderRow[];
      };
      if (!veri?.ok) {
        setNotice("Sağlayıcılar okunamadı.");
        return;
      }
      setRows(veri.saglayicilar ?? []);
    } catch {
      setNotice("Sağlayıcılar okunamadı.");
    }
  }, [client]);

  useEffect(() => {
    void load();
    const running = timers.current;
    return () => running.forEach((id) => window.clearTimeout(id));
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase("tr");
    if (!q) return rows;
    return rows.filter((row) => row.ad.toLocaleLowerCase("tr").includes(q));
  }, [query, rows]);

  useEffect(() => {
    const row = rows.find((item) => item.id === open);
    setReveal(false);
    if (!row || row.tur !== "anahtar" || !row.bagli) { setSecret(""); setStored(""); return; }
    let alive = true;
    void client.request("kontrol.anahtar_goster", { saglayici: row.id }).then((result) => {
      if (!alive) return;
      const value = result.ok && typeof result.deger === "string" ? result.deger : "";
      setStored(value);
      setSecret(value);
    }).catch(() => undefined);
    return () => { alive = false; };
  }, [client, open, rows]);

  useEffect(() => {
    const row = rows.find((item) => item.id === open);
    if (!row?.bagli || row.tur !== "web") return;
    let alive = true;
    setModelLoading(row.id);
    setModelError(null);
    void client.request("web.model_secenekleri", {
      saglayici: row.id,
      hesap: row.hesap ?? "main",
    }).then((result) => {
      if (!alive) return;
      if (result.ok && Array.isArray(result.secenekler)) {
        setModelChoices((current) => ({
          ...current,
          [row.id]: (result.secenekler as unknown[]).filter(
            (value): value is string => typeof value === "string",
          ),
        }));
      } else {
        setModelError(String(result.metin ?? "Web model menüsü okunamadı."));
      }
    }).catch(() => {
      if (alive) setModelError("Web model menüsü okunamadı.");
    }).finally(() => {
      if (alive) setModelLoading(null);
    });
    return () => { alive = false; };
  // Yalnız açılan kart veya bağlantı değişince canlı menü yeniden okunur.
  }, [client, open, rows]);

  const selectWebModel = async (row: ProviderRow, choice: string) => {
    setBusy(row.id);
    const result = await client.request("web.model_sec", {
      saglayici: row.id,
      hesap: row.hesap ?? "main",
      secim: choice,
    });
    setBusy(null);
    setNotice(String(result.metin ?? (result.ok ? `${row.ad}: ${choice} seçildi.` : "Model seçilemedi.")));
    if (result.ok) {
      await load();
      onChanged();
    }
  };

  /**
   * Web girişini aç; pencere kapanınca oturumu KAYDET ve gerçekten sına.
   *
   * Eskiden yalnız pencere kapanınca liste tazeleniyordu ve "bağlı" kararı
   * tarayıcı profili klasörünün varlığından veriliyordu. Giriş yapmadan
   * pencereyi kapatmak bile "bağlı" gösteriyor, Fusion ise o sağlayıcıyı
   * kullanamıyordu. Artık üç adım var: giriş → kayıt → küçük bir gerçek istek.
   */
  const login = async (row: ProviderRow) => {
    const hesap = row.hesap ?? "main";
    setBusy(row.id);
    setNotice(null);
    let acilis: { ok?: boolean; metin?: string; pid?: number };
    try {
      acilis = (await client.request("web.giris", { saglayici: row.id, hesap })) as typeof acilis;
    } catch {
      setBusy(null);
      setNotice("Giriş penceresi başlatılamadı. Fusion'ı kapatıp tekrar aç ve yeniden dene.");
      return;
    }
    if (!acilis?.ok || !acilis.pid) {
      setNotice(acilis?.metin ?? "Giriş penceresi açılamadı.");
      setBusy(null);
      return;
    }
    setNotice("Açılan Chrome'da giriş yap; ardından Chrome menüsünden Çık'ı seç. Oturum otomatik sınanacak.");
    const deadline = Date.now() + GIRIS_SURESI_MS;
    const poll = async () => {
      try {
        if (Date.now() >= deadline) {
          setBusy(null);
          setNotice("Giriş süresi doldu. Giriş Chrome'unu kapatıp yeniden dene.");
          return;
        }
        const durum = (await client.request("web.giris_durumu", { pid: acilis.pid })) as {
          acik?: boolean;
          ok?: boolean;
          metin?: string;
        };
        if (durum.ok === false) {
          setBusy(null);
          setNotice(durum.metin ?? "Giriş işlemi tamamlanamadı.");
          return;
        }
        if (durum?.acik) {
          timers.current.push(window.setTimeout(() => void poll(), YOKLAMA_MS));
          return;
        }
        setNotice("Oturum kaydediliyor…");
        const kayit = (await client.request("web.baglan", { saglayici: row.id, hesap })) as {
          ok?: boolean;
          metin?: string;
        };
        if (!kayit?.ok) {
          setBusy(null);
          setNotice(kayit?.metin ?? "Oturum kaydedilemedi.");
          await load();
          return;
        }
        setNotice("Oturum sınanıyor…");
        const sinama = (await client.request("web.dogrula", { saglayici: row.id, hesap })) as {
          ok?: boolean;
          metin?: string;
        };
        setBusy(null);
        setNotice(
          sinama?.ok
            ? `${row.ad} bağlandı ve çalışıyor.`
            : `${row.ad} kaydedildi ama sınama geçmedi: ${sinama?.metin ?? "sebep bilinmiyor"}`,
        );
        await load();
        onChanged();
      } catch {
        setBusy(null);
        setNotice("Giriş işlemi izlenemedi. Fusion'ı kapatıp tekrar aç ve yeniden dene.");
      }
    };
    await poll();
  };

  /** Kayıtlı oturumu gerçek bir istekle sına. */
  const verify = async (row: ProviderRow) => {
    setBusy(row.id);
    setNotice("Oturum sınanıyor…");
    const sonuc = (await client.request("web.dogrula", {
      saglayici: row.id,
      hesap: row.hesap ?? "main",
    })) as { ok?: boolean; metin?: string; gecikme_ms?: number };
    setBusy(null);
    setNotice(
      sonuc?.ok
        ? `Çalışıyor${sonuc.gecikme_ms ? ` · ${Math.round(sonuc.gecikme_ms)} ms` : ""}.`
        : (sonuc?.metin ?? "Sınama geçmedi."),
    );
  };

  /** Oturumu kapat: kayıt kaldırılır, tarayıcı profili silinir. */
  const logout = async (row: ProviderRow) => {
    setBusy(row.id);
    const sonuc = (await client.request("web.cikis", {
      saglayici: row.id,
      hesap: row.hesap ?? "main",
    })) as { ok?: boolean; metin?: string };
    setBusy(null);
    setNotice(sonuc?.metin ?? (sonuc?.ok ? "Oturum kapatıldı." : "Oturum kapatılamadı."));
    await load();
    if (sonuc?.ok) onChanged();
  };

  const saveKey = async (row: ProviderRow) => {
    if (!secret.trim()) return;
    const submitted = secret;
    setBusy(row.id);
    const sonuc = (await client.request("kontrol.anahtar_kaydet", {
      saglayici: row.id,
      deger: submitted,
    })) as { ok?: boolean; metin?: string };
    setBusy(null);
    if (!sonuc?.ok) {
      setNotice(sonuc?.metin ?? "Anahtar kaydedilemedi.");
      return;
    }
    setStored(submitted);
    setNotice(`${row.ad} anahtarı kaydedildi.`);
    await load();
    onChanged();
  };

  const dropKey = async (row: ProviderRow) => {
    setBusy(row.id);
    const sonuc = (await client.request("kontrol.anahtar_sil", { saglayici: row.id })) as {
      ok?: boolean;
      metin?: string;
    };
    setBusy(null);
    if (!sonuc?.ok) {
      setNotice(sonuc?.metin ?? "Anahtar silinemedi.");
      return;
    }
    setSecret("");
    setStored("");
    setNotice(`${row.ad} anahtarı silindi.`);
    await load();
    onChanged();
  };

  const toggle = (row: ProviderRow) => {
    if (dirty) { setNotice("Kaydedilmemiş anahtar var. Önce Kaydet'e bas veya alanı temizle."); return; }
    setOpen((current) => (current === row.id ? null : row.id));
  };

  const stateText = (row: ProviderRow) => row.tur === "anahtar"
    ? (row.bagli ? "anahtar kayıtlı" : "anahtar yok")
    : row.bagli ? (row.olcum_gecti ? "bağlı · dosya yazabilir" : "bağlı · yalnız okur") : "bağlı değil";

  const detail = (row: ProviderRow) => (
    <div className="pv-detail" key={`detail-${row.id}`} role="region" aria-label={`${row.ad} ayrıntıları`}>
      <div className="pv-detail__head">
        <span className="pv-mark pv-mark--lg">
          {row.tur === "web" ? <ProviderLogo id={row.id as ProviderId} size={22} /> : <span aria-hidden="true">{row.ad.slice(0, 1)}</span>}
        </span>
        <div>
          <h4>{row.ad}</h4>
          <p><span className="pv-dot" data-bagli={row.bagli} aria-hidden="true" /> {stateText(row)}</p>
        </div>
        <button aria-label="Ayrıntıyı kapat" className="pv-close" onClick={() => toggle(row)} type="button">×</button>
      </div>
      {row.eylem === "oturum" ? (
        <div className="pv-detail__body">
          <p>Kendi aboneliğinle çalışır; anahtar gerekmez. Giriş ayrı bir pencerede yapılır ve oturum bu bilgisayarda kalır.</p>
          {row.pencere_kipi && (
            <p className="provider-list__meta">Tarayıcı penceresi: {PENCERE_KIPLERI[row.pencere_kipi] ?? row.pencere_kipi}</p>
          )}
          {row.bagli && (
            <label className="provider-list__model-choice">
              <span>Bu web oturumunda kullanılacak model</span>
              <select
                aria-label={`${row.ad} web modeli`}
                disabled={busy === row.id || modelLoading === row.id || !modelChoices[row.id]}
                onChange={(event) => void run(() => selectWebModel(row, event.target.value))}
                value={row.secili_model ?? "Otomatik"}
              >
                {row.secili_model && modelChoices[row.id] && !modelChoices[row.id].includes(row.secili_model) && (
                  <option disabled value={row.secili_model}>{row.secili_model} (artık sunulmuyor)</option>
                )}
                {(modelChoices[row.id] ?? [row.secili_model ?? "Otomatik"]).map((choice) => (
                  <option key={choice} value={choice}>{choice}</option>
                ))}
              </select>
              <small>{modelError ?? (modelLoading === row.id
                ? "Hesabındaki seçenekler okunuyor…"
                : row.secili_model && modelChoices[row.id] && !modelChoices[row.id].includes(row.secili_model)
                  ? "Seçili model artık yok. Devam etmek için kullanılabilir bir model seç."
                  : "Yalnız bu hesabın canlı menüsünde bulunan modeller gösterilir.")}</small>
            </label>
          )}
          {row.pencere_uyarisi && <p className="provider-list__warn" role="status">{row.pencere_uyarisi}</p>}
          {!row.bagli && row.profil_var && (
            <p className="provider-list__warn">Tarayıcı profili var ama oturum kayıtlı değil — giriş yarım kalmış olabilir. Yeniden bağlan.</p>
          )}
          <div className="provider-list__buttons">
            <button className="provider-list__action provider-list__action--primary" disabled={busy === row.id} onClick={() => void login(row)} type="button">
              {busy === row.id ? "Sürüyor…" : row.bagli ? "Yeniden bağlan" : "Oturum aç"}
            </button>
            {row.bagli && (
              <>
                <button
                  className="provider-list__action"
                  disabled={busy === row.id}
                  onClick={() => void run(async () => {
                    const sonuc = await client.request("web.arac_olc", { saglayici: row.id, hesap: row.hesap ?? "main" });
                    setNotice(String(sonuc?.metin ?? "Ölçüm tamamlanamadı."));
                    await load();
                  })}
                  type="button"
                >
                  {row.olcum_gecti ? "Araç ölçümünü yenile" : "Araç desteğini ölç"}
                </button>
                <button className="provider-list__action" disabled={busy === row.id} onClick={() => void run(() => verify(row))} type="button">Bağlantıyı sına</button>
                <button className="provider-list__action provider-list__action--danger" disabled={busy === row.id} onClick={() => void run(() => logout(row))} type="button">Çıkış yap</button>
              </>
            )}
          </div>
        </div>
      ) : (
        <div className="pv-detail__body">
          <label htmlFor={`key-${row.id}`}>API anahtarı</label>
          <div className="pv-field">
            <input
              autoComplete="off"
              id={`key-${row.id}`}
              disabled={busy !== null}
              onChange={(event) => setSecret(event.target.value)}
              placeholder={row.ortam ?? ""}
              spellCheck={false}
              type={reveal ? "text" : "password"}
              value={secret}
            />
            <button
              aria-label={reveal ? "Anahtarı gizle" : "Anahtarı göster"}
              aria-pressed={reveal}
              className="pv-eye"
              onClick={() => setReveal((value) => !value)}
              title={reveal ? "Gizle" : "Göster"}
              type="button"
            >
              <svg aria-hidden="true" fill="none" height="18" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" viewBox="0 0 24 24" width="18">
                <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" />
                <circle cx="12" cy="12" r="3" />
                {!reveal && <path d="M4 4l16 16" />}
              </svg>
            </button>
          </div>
          <p className="pv-hint">
            {row.bagli
              ? "Kayıtlı anahtar şifreli yerel kasada durur; göz düğmesiyle istediğin zaman görebilirsin."
              : "Anahtar yerel şifreli kasada saklanır ve sonradan buradan görülebilir."}
            {row.ortam ? ` Ortam değişkeni: ${row.ortam}` : ""}
          </p>
          <div className="provider-list__buttons">
            <button className="provider-list__action provider-list__action--primary" disabled={busy === row.id || !dirty} onClick={() => void run(() => saveKey(row))} type="button">Kaydet</button>
            {row.bagli && <button className="provider-list__action" type="button" disabled={busy === row.id} onClick={() => void run(() => verifyKey(row))}>Anahtarı sına</button>}
            {row.bagli && <button className="provider-list__action provider-list__action--danger" disabled={busy === row.id} onClick={() => void run(() => dropKey(row))} type="button">Kayıtlı anahtarı sil</button>}
          </div>
        </div>
      )}
    </div>
  );

  return (
    <section aria-label="Sağlayıcılar" className="provider-list">
      <header className="pv-head">
        <div>
          <h3>Model sağlayıcıları</h3>
          <p>Bir karta dokun: anahtar gir ya da abonelik oturumunu aç.</p>
        </div>
        <input aria-label="Sağlayıcı ara" className="provider-list__search" onChange={(event) => setQuery(event.target.value)} placeholder="Ara" type="search" value={query} />
      </header>

      {notice && <p className="provider-list__notice" role="status">{notice}</p>}

      {filtered.length === 0 && (
        <p className="provider-list__empty">
          {rows.length === 0
            ? "Sağlayıcı listesi boş. Bağlantı kurulamadıysa Fusion'ı yeniden başlat."
            : `"${query.trim()}" ile eşleşen sağlayıcı yok.`}
        </p>
      )}

      {([["web", "Abonelik oturumları", "Kendi ChatGPT, Gemini ya da Claude aboneliğinle; anahtar gerekmez."], ["anahtar", "API anahtarları", "Ücretsiz katmanı olan sağlayıcılar; anahtar şifreli kasada saklanır."]] as const).map(([tur, baslik, aciklama]) => {
        const grup = filtered.filter((row) => row.tur === tur);
        if (grup.length === 0) return null;
        const acik = grup.find((row) => row.id === open);
        return (
          <div className="pv-group" key={tur}>
            <div className="pv-group__title"><h4>{baslik}</h4><p>{aciklama}</p></div>
            <ul className="pv-grid">
              {grup.map((row) => (
                <li key={row.id}>
                  <button
                    aria-expanded={open === row.id}
                    className="pv-card"
                    data-bagli={row.bagli}
                    disabled={busy !== null}
                    onClick={() => toggle(row)}
                    type="button"
                  >
                    <span className="pv-card__top">
                      <span className="pv-mark">
                        {row.tur === "web" ? <ProviderLogo id={row.id as ProviderId} size={20} /> : <span aria-hidden="true">{row.ad.slice(0, 1)}</span>}
                      </span>
                      <span className="pv-dot" data-bagli={row.bagli} aria-hidden="true" />
                    </span>
                    <span className="pv-card__name">{row.ad}</span>
                    <span className="pv-card__state" data-bagli={row.bagli}>{stateText(row)}</span>
                  </button>
                </li>
              ))}
            </ul>
            {acik && detail(acik)}
          </div>
        );
      })}
    </section>
  );
}

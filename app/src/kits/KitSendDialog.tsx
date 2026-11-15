import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useModalFocus } from "../ui/useModalFocus";
import "./KitSendDialog.css";

/** Etkin oturumun RPC'si (`kit.listele`, `kit.gonder`, `kit.durum`). */
export type KitRequest = (name: string, data: Record<string, unknown>) => Promise<Record<string, unknown>>;

interface KitOzeti { id: string; ad: string; fusionIzni: boolean }
interface GelenKaydi { gorevId: string; baslik: string; durum: string; guncellendi: number; hata: string | null }
interface GorevAyrintisi { gorevId: string; sonuc: string | null; hata: string | null }
type Tur = "gorev" | "mesaj";

/** Kits `inboxSchema` ve `tools/kits.py` ile aynı sınırlar. */
const MIN_METIN = 3;
const MAX_METIN = 4000;
const DURUM_ADLARI: Record<string, string> = {
  queued: "Sırada", running: "Çalışıyor", paused: "Duraklatıldı",
  completed: "Tamamlandı", failed: "Başarısız", cancelled: "İptal edildi",
};

function metinHatasi(metin: string): string | null {
  if (metin.trim().length < MIN_METIN) return `Metin en az ${MIN_METIN} karakter olmalı.`;
  if (metin.length > MAX_METIN) return `Metin en fazla ${MAX_METIN} karakter olabilir.`;
  return null;
}

function hataMetni(yanit: Record<string, unknown>, varsayilan: string): string {
  return typeof yanit.metin === "string" && yanit.metin ? yanit.metin : varsayilan;
}

function kitleriOku(yanit: Record<string, unknown>): KitOzeti[] {
  const ham = Array.isArray(yanit.kitler) ? yanit.kitler : [];
  return ham.flatMap((kit: unknown) => {
    if (!kit || typeof kit !== "object") return [];
    const { id, name, fusionAllowed } = kit as Record<string, unknown>;
    if (typeof id !== "string" || !id) return [];
    return [{ id, ad: typeof name === "string" && name ? name : id, fusionIzni: fusionAllowed === true }];
  });
}

function kayitlariOku(yanit: Record<string, unknown>): GelenKaydi[] {
  const ham = Array.isArray(yanit.kayitlar) ? yanit.kayitlar : [];
  return ham.flatMap((kayit: unknown) => {
    if (!kayit || typeof kayit !== "object") return [];
    const { taskId, title, status, updatedAt, error } = kayit as Record<string, unknown>;
    if (typeof taskId !== "string") return [];
    return [{
      gorevId: taskId,
      baslik: typeof title === "string" && title ? title : "Başlıksız görev",
      durum: typeof status === "string" ? status : "",
      guncellendi: typeof updatedAt === "number" ? updatedAt : 0,
      hata: typeof error === "string" ? error : null,
    }];
  });
}

function zaman(ms: number): string {
  return ms > 0 ? new Date(ms).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" }) : "";
}

interface KitSendDialogProps {
  /** Kutuya önceden konan metin (ör. Fusion'ın yanıtı); kullanıcı değiştirebilir. */
  initialText: string;
  request: KitRequest;
  onClose: () => void;
}

/**
 * Fusion sohbetinden bir Kit'in gelen kutusuna görev/mesaj bırakır ve o Kit'in gelen
 * kutusunu gösterir. Ölçüldü (31 Ekim, inceleme): `kit.*` RPC'lerinin masaüstünde
 * tüketicisi yoktu; gönderilen işin durumu yalnız modelin yorumundan öğreniliyordu.
 */
export function KitSendDialog({ initialText, request, onClose }: KitSendDialogProps) {
  const ref = useRef<HTMLDivElement>(null);
  useModalFocus(ref, true, onClose, "select, textarea");
  const [kitler, setKitler] = useState<KitOzeti[] | null>(null);
  const [kitId, setKitId] = useState("");
  const [tur, setTur] = useState<Tur>("gorev");
  const [baslik, setBaslik] = useState("");
  const [metin, setMetin] = useState(initialText);
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [hata, setHata] = useState<string | null>(null);
  const [makbuz, setMakbuz] = useState<string | null>(null);
  const [kayitlar, setKayitlar] = useState<GelenKaydi[] | null>(null);
  const [kutuHatasi, setKutuHatasi] = useState<string | null>(null);
  const [ayrinti, setAyrinti] = useState<GorevAyrintisi | null>(null);
  // Kit değiştikten sonra gelen eski yanıt yeni Kit'in listesinin üstüne yazılmasın.
  const kutuSirasi = useRef(0);

  useEffect(() => {
    let etkin = true;
    request("kit.listele", {})
      .then((yanit) => {
        if (!etkin) return;
        if (yanit.ok !== true) { setKitler([]); setHata(hataMetni(yanit, "Kits listesi alınamadı.")); return; }
        const liste = kitleriOku(yanit);
        setKitler(liste);
        setKitId((liste.find((kit) => kit.fusionIzni) ?? liste[0])?.id ?? "");
        if (liste.length === 0) setHata("Kits'te hiç Kit yok; Fusion ana menüsünden Kits bölümünde bir Kit ekle.");
      })
      .catch((reason: unknown) => {
        if (!etkin) return;
        setKitler([]);
        setHata(reason instanceof Error ? reason.message : "Kits listesi alınamadı.");
      });
    return () => { etkin = false; };
  }, [request]);

  const kutuyuYenile = useCallback(async (kit: string) => {
    const sira = ++kutuSirasi.current;
    setKutuHatasi(null);
    try {
      const yanit = await request("kit.durum", { kit });
      if (sira !== kutuSirasi.current) return;
      if (yanit.ok !== true) { setKayitlar([]); setKutuHatasi(hataMetni(yanit, "Gelen kutusu okunamadı.")); return; }
      setKayitlar(kayitlariOku(yanit));
    } catch (reason: unknown) {
      if (sira !== kutuSirasi.current) return;
      setKayitlar([]);
      setKutuHatasi(reason instanceof Error ? reason.message : "Gelen kutusu okunamadı.");
    }
  }, [request]);

  useEffect(() => {
    setAyrinti(null);
    setKayitlar(null);
    if (kitId) void kutuyuYenile(kitId);
  }, [kitId, kutuyuYenile]);

  const secili = kitler?.find((kit) => kit.id === kitId) ?? null;
  const gonderilebilir = Boolean(secili?.fusionIzni) && !gonderiliyor;

  const gonder = async () => {
    if (!secili) return;
    const neden = metinHatasi(metin);
    setMakbuz(null);
    if (neden) { setHata(neden); return; }
    setHata(null);
    setGonderiliyor(true);
    try {
      const veri: Record<string, unknown> = { kit: secili.id, metin, tur, ...(baslik.trim() ? { baslik: baslik.trim() } : {}) };
      const yanit = await request("kit.gonder", veri);
      if (yanit.ok !== true) { setHata(hataMetni(yanit, "Kit'e gönderilemedi.")); return; }
      setMakbuz(`«${secili.ad}» Kit'inin gelen kutusuna kuyruğa alındı. Kit işi kendi sırası gelince yapar; durumu aşağıdan izle.`);
      await kutuyuYenile(secili.id);
    } catch (reason: unknown) {
      setHata(reason instanceof Error ? reason.message : "Kit'e gönderilemedi.");
    } finally {
      setGonderiliyor(false);
    }
  };

  const ayrintiAc = async (kayit: GelenKaydi) => {
    try {
      const yanit = await request("kit.durum", { kit: kitId, gorev_id: kayit.gorevId });
      if (yanit.ok !== true) { setKutuHatasi(hataMetni(yanit, "Görev okunamadı.")); return; }
      setAyrinti({
        gorevId: kayit.gorevId,
        sonuc: typeof yanit.result === "string" ? yanit.result : null,
        hata: typeof yanit.error === "string" ? yanit.error : null,
      });
    } catch (reason: unknown) {
      setKutuHatasi(reason instanceof Error ? reason.message : "Görev okunamadı.");
    }
  };

  return createPortal(
    <div className="kit-send__backdrop">
      <div aria-labelledby="kit-send-title" aria-modal="true" className="kit-send" ref={ref} role="dialog" tabIndex={-1}>
        <header className="kit-send__header">
          <h2 id="kit-send-title">Kit'e gönder</h2>
          <button aria-label="Kapat" className="kit-send__close" onClick={onClose} type="button">×</button>
        </header>
        <p className="kit-send__lead">Metin seçtiğin Kit'in “Fusion gelen kutusu” sohbetine düşer; Kit işi kendi araçları ve izinleriyle yapar.</p>
        <label className="kit-send__field">
          <span>Kit</span>
          <select disabled={!kitler?.length} onChange={(event) => setKitId(event.target.value)} value={kitId}>
            {kitler === null && <option value="">Kit'ler yükleniyor…</option>}
            {kitler?.map((kit) => <option key={kit.id} value={kit.id}>{kit.fusionIzni ? kit.ad : `${kit.ad} (Fusion izni kapalı)`}</option>)}
          </select>
        </label>
        {secili && !secili.fusionIzni && <p className="kit-send__hint">Bu Kit'in Fusion izni kapalı. Kits'te Kit'i düzenle &gt; Fusion iznini aç.</p>}
        <fieldset className="kit-send__kind">
          <legend>Tür</legend>
          <label><input checked={tur === "gorev"} name="kit-send-tur" onChange={() => setTur("gorev")} type="radio" />Görev</label>
          <label><input checked={tur === "mesaj"} name="kit-send-tur" onChange={() => setTur("mesaj")} type="radio" />Mesaj</label>
        </fieldset>
        <label className="kit-send__field">
          <span>Başlık (isteğe bağlı)</span>
          <input maxLength={120} onChange={(event) => setBaslik(event.target.value)} value={baslik} />
        </label>
        <label className="kit-send__field">
          <span>Gönderilecek metin</span>
          <textarea maxLength={MAX_METIN} onChange={(event) => setMetin(event.target.value)} rows={6} value={metin} />
        </label>
        <small aria-live="polite" className="kit-send__count">{metin.length}/{MAX_METIN}</small>
        {hata && <p className="kit-send__error" role="alert">{hata}</p>}
        {makbuz && <p className="kit-send__receipt" role="status">{makbuz}</p>}
        <footer className="kit-send__footer">
          <button className="kit-send__secondary" onClick={onClose} type="button">Vazgeç</button>
          <button className="kit-send__primary" disabled={!gonderilebilir} onClick={() => void gonder()} type="button">
            {gonderiliyor ? "Gönderiliyor…" : "Kit'e gönder"}
          </button>
        </footer>
        {secili && (
          <section aria-labelledby="kit-send-inbox" className="kit-send__inbox">
            <header className="kit-send__header">
              <h3 id="kit-send-inbox">«{secili.ad}» gelen kutusu</h3>
              <button className="kit-send__secondary" onClick={() => void kutuyuYenile(secili.id)} type="button">Yenile</button>
            </header>
            {kutuHatasi && <p className="kit-send__error" role="alert">{kutuHatasi}</p>}
            {kayitlar === null && !kutuHatasi && <p className="kit-send__hint">Gelen kutusu okunuyor…</p>}
            {kayitlar?.length === 0 && !kutuHatasi && <p className="kit-send__hint">Bu Kit'e Fusion'dan henüz bir şey gönderilmedi.</p>}
            {kayitlar && kayitlar.length > 0 && (
              <ul>
                {kayitlar.map((kayit) => (
                  <li key={kayit.gorevId}>
                    <button aria-expanded={ayrinti?.gorevId === kayit.gorevId} className="kit-send__item" onClick={() => void ayrintiAc(kayit)} type="button">
                      <span>{kayit.baslik}</span>
                      <span className={`kit-send__status kit-send__status--${kayit.durum}`}>{DURUM_ADLARI[kayit.durum] ?? kayit.durum}</span>
                      <time>{zaman(kayit.guncellendi)}</time>
                    </button>
                    {ayrinti?.gorevId === kayit.gorevId && (
                      ayrinti.hata ? <p className="kit-send__error">{ayrinti.hata}</p>
                        : ayrinti.sonuc ? <pre className="kit-send__result">{ayrinti.sonuc}</pre>
                        : <p className="kit-send__hint">Henüz sonuç yok.</p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        )}
      </div>
    </div>,
    document.body,
  );
}

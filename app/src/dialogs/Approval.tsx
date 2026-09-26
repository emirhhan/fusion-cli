import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { Soru } from "../protocol/types";
import { DiffCard } from "../markdown/DiffCard";
import "./Approval.css";

interface ApprovalProps {
  onCevap: (veri: Record<string, unknown>) => void;
  soru: Soru;
  /** Kartın üst etiketi; verilmezse türe göre "İzin gerekiyor"/"Fusion soruyor". */
  eyebrow?: string;
  /** "Diğer" seçeneği sunulsun mu? (Yalnız soru kartı; varsayılan açık.) */
  serbestCevap?: boolean;
}

interface Secenek {
  /** Çekirdeğe gidecek cevap. */
  cevap: Record<string, unknown>;
  etiket: string;
  aciklama?: string;
  onerilen: boolean;
  reddet: boolean;
}

/** Çekirdek argümanları `ad='değer'` listesi olarak gönderir; eski biçim sözlüktü. */
function argumanSatirlari(argumanlar: Soru["argumanlar"]): string[] {
  if (!argumanlar) return [];
  if (Array.isArray(argumanlar)) return argumanlar.map(String);
  return Object.entries(argumanlar).map(([ad, deger]) => `${ad}=${String(deger)}`);
}

function secenekler(soru: Soru): Secenek[] {
  const onerilen = soru.onerilen ?? null;
  if (soru.tur === "soru") {
    return (soru.secenekler ?? []).map((secenek) => ({
      cevap: { metin: secenek.etiket },
      etiket: secenek.etiket,
      aciklama: secenek.aciklama,
      onerilen: secenek.etiket === onerilen,
      reddet: false,
    }));
  }
  const ilkOlumlu = (soru.secenekler ?? []).find((secenek) => secenek.deger !== "deny")?.deger;
  return (soru.secenekler ?? []).map((secenek) => ({
    cevap: { secim: secenek.deger },
    etiket: secenek.etiket,
    aciklama: secenek.aciklama,
    onerilen: secenek.deger === (onerilen ?? ilkOlumlu),
    reddet: secenek.deger === "deny",
  }));
}

/**
 * İzin ve soru kartı — Claude Code'daki gibi composer'ın hemen üstünde,
 * composer genişliğinde, ekranı kapatmayan kompakt bir kart.
 *
 * Aynı bileşen iki şeyi çizer:
 * - `onay`: aracın ne yapacağını tek cümleyle söyler, hedefi (komut, dosya)
 *   olduğu gibi gösterir; düzenlemede diff, yıkıcı işlemde uyarı.
 * - `soru`: modelin `ask_user` sorusu; seçenekler + "Diğer" ile serbest cevap.
 *   Eskiden sorular izin penceresinde çiziliyor ve cevap `secim` alanıyla
 *   gidiyordu; çekirdek `metin` beklediği için model cevabı hiç alamıyordu.
 *
 * Klavye: 1-9 seçer, ↑/↓ gezinir, Enter onaylar, Esc reddeder / soruyu atlar.
 */
export function Approval({ soru, onCevap, eyebrow, serbestCevap = true }: ApprovalProps) {
  const kartRef = useRef<HTMLElement>(null);
  const digerRef = useRef<HTMLInputElement>(null);
  const [digerAcik, setDigerAcik] = useState(soru.tur === "soru" && !(soru.secenekler ?? []).length);
  const [digerMetin, setDigerMetin] = useState("");
  const liste = secenekler(soru);
  const soruMu = soru.tur === "soru";
  const baslik = soruMu ? soru.soru ?? "Fusion bir şey soruyor" : soru.baslik ?? "Bu işleme izin verilsin mi?";
  const ayrintilar = argumanSatirlari(soru.argumanlar);
  const reddet = liste.find((secenek) => secenek.reddet);

  useEffect(() => {
    if (digerAcik) digerRef.current?.focus();
    else kartRef.current?.focus();
  }, [digerAcik]);

  const sec = (secenek: Secenek) => onCevap(secenek.cevap);
  const digeriGonder = () => {
    if (digerMetin.trim()) onCevap({ metin: digerMetin.trim() });
  };
  const vazgec = () => {
    if (soruMu) onCevap({ metin: "" });
    else if (reddet) sec(reddet);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      vazgec();
      return;
    }
    if (event.target instanceof HTMLInputElement) return;
    const sira = Number(event.key);
    if (Number.isInteger(sira) && sira >= 1) {
      event.preventDefault();
      if (sira <= liste.length) sec(liste[sira - 1]);
      else if (soruMu && sira === liste.length + 1) setDigerAcik(true);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const dugmeler = Array.from(kartRef.current?.querySelectorAll<HTMLButtonElement>(".prompt-card__option") ?? []);
      const simdiki = dugmeler.indexOf(document.activeElement as HTMLButtonElement);
      const sonraki = event.key === "ArrowDown" ? simdiki + 1 : simdiki - 1;
      dugmeler[(sonraki + dugmeler.length) % dugmeler.length]?.focus();
    }
  };

  return (
    <div className="prompt-dock">
      <section
        aria-labelledby="prompt-card-title"
        className="prompt-card"
        data-kind={soruMu ? "soru" : "onay"}
        data-danger={soru.tehlike ? "true" : undefined}
        onKeyDown={onKeyDown}
        ref={kartRef}
        role="dialog"
        tabIndex={-1}
      >
        <div className="prompt-card__eyebrow">{eyebrow ?? (soruMu ? "Fusion soruyor" : "İzin gerekiyor")}</div>
        <h2 className="prompt-card__title" id="prompt-card-title">{baslik}</h2>
        {!soruMu && soru.hedef && !soru.diff && <pre className="prompt-card__target">{soru.hedef}</pre>}
        {soru.tehlike && <p className="prompt-card__danger">Dikkat: {soru.tehlike}</p>}
        {soru.diff && (
          <div className="prompt-card__diff">
            {/* Karar argümandan değil SONUCUNDAN verilir: ne değişecek, burada. */}
            <DiffCard diff={soru.diff} path={soru.hedef ?? ""} />
          </div>
        )}
        {!soruMu && ayrintilar.length > 0 && (
          <details className="prompt-card__details">
            <summary>Ayrıntılar · {soru.arac}</summary>
            <ul>{ayrintilar.map((satir) => <li key={satir}>{satir}</li>)}</ul>
          </details>
        )}
        <div className="prompt-card__options" role="group" aria-label="Seçenekler">
          {liste.map((secenek, index) => (
            <button
              className="prompt-card__option"
              data-recommended={secenek.onerilen || undefined}
              data-deny={secenek.reddet || undefined}
              key={secenek.etiket}
              onClick={() => sec(secenek)}
              type="button"
            >
              <span aria-hidden="true" className="prompt-card__key">{index + 1}</span>
              <span className="prompt-card__label">
                {secenek.etiket}
                {secenek.aciklama && <small>{secenek.aciklama}</small>}
              </span>
              {secenek.onerilen && soruMu && <span className="prompt-card__badge">Önerilen</span>}
            </button>
          ))}
          {soruMu && serbestCevap && !digerAcik && (
            <button className="prompt-card__option" onClick={() => setDigerAcik(true)} type="button">
              <span aria-hidden="true" className="prompt-card__key">{liste.length + 1}</span>
              <span className="prompt-card__label">Diğer…<small>Kendi cevabını yaz</small></span>
            </button>
          )}
          {soruMu && digerAcik && (
            <form className="prompt-card__other" onSubmit={(event) => { event.preventDefault(); digeriGonder(); }}>
              <input
                aria-label="Cevabın"
                onChange={(event) => setDigerMetin(event.target.value)}
                placeholder="Cevabını yaz ve Enter'a bas"
                ref={digerRef}
                value={digerMetin}
              />
              <button disabled={!digerMetin.trim()} type="submit">Gönder</button>
            </form>
          )}
        </div>
        <p className="prompt-card__hint">
          {soruMu ? "Sayıyla seç · Esc soruyu atla" : `Sayıyla seç · Esc ${reddet ? "reddet" : "kapat"}`}
        </p>
      </section>
    </div>
  );
}

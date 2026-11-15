import { useCallback, useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../../protocol/client";
import { errorMessage, operationResult } from "../../protocol/result";
import { Button } from "../../ui/Button";
import { ToggleRow } from "../PanelParts";

/**
 * Ayarlar › İzinler › Kabuk sandbox'ı (P-010; Claude Code `/sandbox` paneli).
 *
 * `sandbox.durum` platformu ve sandbox'ın bu makinede kurulup kurulamadığını söyler;
 * `sandbox.ayarla` aç/kapat, ağ kipi, alan adı listeleri ve davranış bayraklarını
 * kullanıcı yapılandırmasına yazar. Değişiklik bir sonraki görevde uygulanır.
 * Yanıttaki `notlar` (ör. "ağ kipi allowlist'e geçti") kartta gösterilir.
 */

export interface SandboxStatus {
  ok?: boolean;
  metin?: string;
  acik: boolean;
  platform: string;
  kullanilabilir: boolean;
  neden: string;
  ag: "open" | "allowlist";
  izinli_alanlar: string[];
  yasak_alanlar: string[];
  localhost: boolean;
  ek_yazma: string[];
  okuma_engeli: string[];
  /** Varsayılan okuma engelinden bilerek açılan yollar (`sandbox.allow_read`); eski çekirdek göndermez. */
  okuma_izni?: string[];
  /** Fusion Chrome'unun hata ayıklama (CDP) portu korumasının kapsamı; eski çekirdek göndermez. */
  cdp_korumasi?: string;
  zorunlu: boolean;
  disari_izinli: boolean;
  oto_izin: boolean;
  disari_komutlar: string[];
  /** Eski çekirdek göndermeyebilir; yoksa anahtar gizlenir. */
  sir_ortami_gizli?: boolean;
  /** Etkin ek Claude anahtarları (kendi proxy, tlsTerminate, mask…); eski çekirdek göndermez. */
  ek_ayarlar?: string[];
  /** Yalnız `sandbox.ayarla` yanıtında: değişikliğin yan etkileri (ağ kipi değişti…). */
  notlar?: string[];
}

type SandboxAction =
  | "ac" | "kapat" | "ag" | "izin" | "engelle" | "kaldir"
  | "oto" | "zorunlu" | "disari" | "sir" | "localhost";

function isStatus(value: unknown): value is SandboxStatus {
  return Boolean(value) && typeof value === "object" && typeof (value as SandboxStatus).platform === "string";
}

export function SandboxCard({ client }: { client: ProtocolClient }) {
  const [status, setStatus] = useState<SandboxStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [alan, setAlan] = useState("");
  const [karar, setKarar] = useState<"izin" | "engelle">("izin");
  const [notlar, setNotlar] = useState<string[]>([]);
  const owner = useRef(0);

  const load = useCallback(async () => {
    const generation = owner.current;
    try {
      const payload = await client.request("sandbox.durum", {});
      if (generation !== owner.current) return;
      if (isStatus(payload)) { setStatus(payload); setError(null); }
    } catch (reason) {
      if (generation === owner.current) setError(`Sandbox durumu okunamadı: ${errorMessage(reason)}`);
    }
  }, [client]);

  useEffect(() => {
    const generation = ++owner.current;
    void load();
    return () => { owner.current = generation + 1; };
  }, [load]);

  const act = async (islem: SandboxAction, deger: string | boolean = "") => {
    if (busy) return false;
    setBusy(true); setError(null); setNotlar([]);
    const generation = owner.current;
    try {
      const payload = await client.request("sandbox.ayarla", { islem, deger });
      if (generation !== owner.current) return false;
      const result = operationResult(payload, "Sandbox ayarı kaydedilemedi.");
      if (!result.ok) { setError(result.message); return false; }
      if (isStatus(payload)) { setStatus(payload); setNotlar(payload.notlar ?? []); }
      return true;
    } catch (reason) {
      if (generation === owner.current) setError(errorMessage(reason));
      return false;
    } finally {
      if (generation === owner.current) setBusy(false);
    }
  };

  const addDomain = async () => {
    const metin = alan.trim();
    if (metin && (await act(karar, metin))) setAlan("");
  };

  if (!status && !error) return null;
  const allowlist = status?.ag === "allowlist";

  return (
    <article className="settings__card settings__card--wide" id="settings-sandbox">
      <div className="settings__card-head">
        <div>
          <h3>Kabuk sandbox&apos;ı</h3>
          <p className="settings__hint">
            Açıkken komutlar işletim sisteminin sandbox&apos;ında çalışır: yazma yalnız proje klasörüne ve
            eklenen dizinlere, okuma ve ağ aşağıdaki kurallarla sınırlıdır. Değişiklik sonraki görevde geçerli olur.
          </p>
        </div>
      </div>
      {error && <p className="settings__hint" role="alert">{error}</p>}
      {notlar.length > 0 && (
        <div aria-live="polite" className="sandbox__notes">
          {notlar.map((not) => <p className="settings__hint" key={not}>{not}</p>)}
        </div>
      )}
      {status && (
        <>
          <ToggleRow
            checked={status.acik}
            chip={status.platform}
            description="Kapalıyken komutlar kısıtsız çalışır (yalnız onay ve izin kuralları geçerlidir)."
            disabled={busy}
            onChange={(deger) => void act(deger ? "ac" : "kapat")}
            title="Sandbox'ı aç"
            warning={status.kullanilabilir ? undefined : `Kurulamaz: ${status.neden}`}
          />
          <div className="settings__choices" role="group" aria-label="Sandbox ağı">
            {([
              ["open", "Ağ açık", "Komutlar her adrese bağlanabilir."],
              ["allowlist", "Yalnız izinli alan adları", "Dış ağ yalnız Fusion proxy'si üzerinden, listedeki alan adlarına açık."],
            ] as const).map(([kip, etiket, aciklama]) => (
              <button
                aria-pressed={status.ag === kip}
                className="settings__choice"
                data-active={status.ag === kip}
                disabled={busy}
                key={kip}
                onClick={() => { if (status.ag !== kip) void act("ag", kip); }}
                type="button"
              >
                <strong>{etiket}</strong>
                <small>{aciklama}</small>
              </button>
            ))}
          </div>
          {allowlist && (
            <div className="sandbox__domains">
              <ToggleRow
                checked={status.localhost}
                description="Yerel geliştirme sunucusu ve veritabanı (localhost) açık kalır. Fusion'ın web profil tarayıcısının hata ayıklama portu bu izinle de kapalıdır."
                disabled={busy}
                onChange={(deger) => void act("localhost", deger)}
                title="localhost'a izin ver"
              />
              {status.izinli_alanlar.length === 0 && status.yasak_alanlar.length === 0 && (
                <p className="settings__hint">Liste boş: dış ağ tamamen kapalı{status.localhost ? ", localhost açık" : ""}.</p>
              )}
              <ul aria-label="Alan adları" className="sandbox__list">
                {[
                  ...status.izinli_alanlar.map((ad) => ({ ad, yasak: false })),
                  ...status.yasak_alanlar.map((ad) => ({ ad, yasak: true })),
                ].map(({ ad, yasak }) => (
                  <li data-denied={yasak} key={`${yasak}:${ad}`}>
                    <code>{ad}</code>
                    <span className="permissions__decision" data-decision={yasak ? "deny" : "allow"}>{yasak ? "Yasak" : "İzinli"}</span>
                    <Button
                      aria-label={`${ad} alan adını kaldır`}
                      disabled={busy}
                      icon="close"
                      iconOnly
                      onClick={() => void act("kaldir", ad)}
                    />
                  </li>
                ))}
              </ul>
              <form className="permissions__add sandbox__add" onSubmit={(event) => { event.preventDefault(); void addDomain(); }}>
                <select aria-label="Alan adı kararı" disabled={busy} onChange={(event) => setKarar(event.target.value as "izin" | "engelle")} value={karar}>
                  <option value="izin">İzin ver</option>
                  <option value="engelle">Yasakla</option>
                </select>
                <input
                  aria-label="Alan adı"
                  disabled={busy}
                  onChange={(event) => setAlan(event.target.value)}
                  placeholder="github.com ya da *.npmjs.org"
                  spellCheck={false}
                  value={alan}
                />
                <Button disabled={busy || !alan.trim()} type="submit" variant="primary">Alan adı ekle</Button>
              </form>
            </div>
          )}
          <div className="permissions__blocks">
            <ToggleRow
              checked={status.oto_izin}
              description="Sandbox içinde ve ağ yalnız izinli alan adlarındayken komutlar onay sormadan çalışır. Yıkıcı komutlar, 'her zaman sor' kuralları ve plan kipi yine geçerlidir."
              disabled={busy}
              onChange={(deger) => void act("oto", deger)}
              title="Sandbox içindeki komutları sormadan çalıştır"
              warning={status.oto_izin && !allowlist ? "Ağ açıkken etkisiz: yalnız 'Yalnız izinli alan adları' kipinde sorulmadan çalışır." : undefined}
            />
            <ToggleRow
              checked={status.disari_izinli}
              description="Model bir komutu sandbox dışında çalıştırmak isteyebilir; bu istek her seferinde ayrıca sorulur. Kapalıyken istek yok sayılır."
              disabled={busy}
              onChange={(deger) => void act("disari", deger)}
              title="Sandbox dışı isteğe izin ver"
            />
            <ToggleRow
              checked={status.zorunlu}
              description="Sandbox bu makinede kurulamazsa komut çalıştırılmaz. Kapalıyken bir kez uyarılır ve komut sandbox'sız çalışır."
              disabled={busy}
              onChange={(deger) => void act("zorunlu", deger)}
              title="Sandbox kurulamazsa çalıştırma"
            />
            {typeof status.sir_ortami_gizli === "boolean" && (
              <ToggleRow
                checked={status.sir_ortami_gizli}
                description="Adı sır gibi görünen ortam değişkenleri (*_TOKEN, *_API_KEY…) sandbox'taki komuta verilmez. Kaza önleyicidir, güvenlik sınırı değildir."
                disabled={busy}
                onChange={(deger) => void act("sir", deger)}
                title="Sır ortam değişkenlerini gizle"
              />
            )}
          </div>
          {status.cdp_korumasi && (
            <p className="settings__hint">Tarayıcı hata ayıklama portu: {status.cdp_korumasi}.</p>
          )}
          <details className="sandbox__paths">
            <summary>Okunamayan yollar ({status.okuma_engeli.length})</summary>
            <ul>{status.okuma_engeli.map((yol) => <li key={yol}><code>{yol}</code></li>)}</ul>
            {(status.okuma_izni ?? []).length > 0 && (
              <p className="settings__hint">
                Varsayılan engelden bilerek açılanlar: {(status.okuma_izni ?? []).map((yol) => <code key={yol}>{yol} </code>)}
              </p>
            )}
          </details>
          {(status.ek_ayarlar ?? []).length > 0 && (
            <ul className="settings__hint" aria-label="Ek sandbox ayarları">
              {(status.ek_ayarlar ?? []).map((satir) => <li key={satir}>{satir}</li>)}
            </ul>
          )}
          <p className="settings__hint">
            Ek yazma dizini, okuma listesi ve sandbox dışı komutlar: <code>/config sandbox.allow_write=~/.npm</code>,{" "}
            <code>/config sandbox.deny_read=~/ozel</code> (varsayılana eklenir),{" "}
            <code>/config sandbox.allow_read=~/.kube</code> (varsayılandan çıkarır),{" "}
            <code>/config sandbox.excluded_commands=docker</code>.
            {status.disari_komutlar.length > 0 && <> Sandbox dışı: {status.disari_komutlar.join(", ")}.</>}
          </p>
        </>
      )}
    </article>
  );
}

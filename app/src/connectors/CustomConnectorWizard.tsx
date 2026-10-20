import { useState } from "react";
import { Button } from "../ui/Button";
import type { ConnectorTransport } from "./catalog";

/**
 * Özel MCP sunucusu ekleme sihirbazı — iki adım.
 *
 * Eskiden tek bir formdu: en üstte "Tür" açılır kutusu, altında ad, altında
 * türe göre değişen alanlar ve en altta farklı boylarda düğmeler. Kullanıcının
 * ölçülmüş tepkisi "orantısız büyük küçük butonların olduğu kötü bir ekran"
 * idi ve haklıydı — form neyi neden sorduğunu hiç söylemiyordu.
 *
 * Şimdi önce NE eklediğin seçilir (üç kart, her biri ne işe yaradığını yazar),
 * sonra yalnız o türün alanları sorulur.
 */

export type WizardTransport = ConnectorTransport | "hosted";

interface TurSecenegi {
  id: WizardTransport;
  baslik: string;
  aciklama: string;
}

const TURLER: TurSecenegi[] = [
  {
    id: "stdio",
    baslik: "Yerel komut",
    aciklama:
      "Bilgisayarında çalışan bir MCP sunucusu. Fusion komutu kendi başlatır; " +
      "giriş yapmak gerekmez.",
  },
  {
    id: "streamable_http",
    baslik: "Uzak MCP",
    aciklama:
      "İnternetteki bir MCP adresi. Gerekirse OAuth ile giriş yapılır ya da " +
      "hazır bir erişim token'ı verilir.",
  },
  {
    id: "hosted",
    baslik: "Sağlayıcı üzerinden",
    aciklama:
      "Araçlar Fusion'da değil, giriş yaptığın web sağlayıcısının kendi " +
      "connector ekranında çalışır. Token Fusion'a hiç gelmez.",
  },
];

export interface HostedProvider {
  adres: string;
  ad: string;
  hazir: boolean;
  id: string;
}

export interface WizardValue {
  ad: string;
  client_id: string;
  kapsamlar: string;
  komut: string;
  saglayici: string;
  tasima: WizardTransport;
  token: string;
  url: string;
}

export interface CustomConnectorWizardProps {
  deger: WizardValue;
  mesgul: boolean;
  /** `hosted` seçilince okunur; `null` ise henüz yükleniyor. */
  saglayicilar: HostedProvider[] | null;
  /** OAuth dönüş adresi; kendi Client ID'sini kullanan için gerekli. */
  oauthDonusAdresi: string;
  onChange: (deger: WizardValue) => void;
  onSubmit: () => void;
  onCancel: () => void;
}

export function CustomConnectorWizard({
  deger,
  mesgul,
  oauthDonusAdresi,
  onCancel,
  onChange,
  onSubmit,
  saglayicilar,
}: CustomConnectorWizardProps) {
  const [adim, setAdim] = useState<1 | 2>(1);
  const set = (parca: Partial<WizardValue>) => onChange({ ...deger, ...parca });
  const hazirSaglayici = saglayicilar?.some((item) => item.hazir) ?? false;

  const gonderilebilir = Boolean(
    deger.ad.trim() &&
      (deger.tasima === "stdio"
        ? deger.komut.trim()
        : deger.url.trim()) &&
      // Barındırmalı bağlantı, taşıyacak bir oturum olmadan kaydedilemez: kayıt
      // edilir ama hiç çalışmaz ve kullanıcı sebebini anlamazdı.
      (deger.tasima !== "hosted" || (hazirSaglayici && Boolean(deger.saglayici))),
  );

  if (adim === 1) {
    return (
      <div className="wizard">
        <p className="wizard__lead">Ne eklemek istiyorsun?</p>
        <div className="wizard__choices">
          {TURLER.map((tur) => (
            <button
              aria-pressed={deger.tasima === tur.id}
              className="wizard__choice"
              key={tur.id}
              onClick={() => {
                set({ tasima: tur.id });
                setAdim(2);
              }}
              type="button"
            >
              <strong>{tur.baslik}</strong>
              <small>{tur.aciklama}</small>
            </button>
          ))}
        </div>
        <div className="wizard__foot">
          <Button onClick={onCancel} variant="secondary">Vazgeç</Button>
        </div>
      </div>
    );
  }

  const secili = TURLER.find((tur) => tur.id === deger.tasima);

  return (
    <div className="wizard">
      <div className="wizard__step-head">
        <button className="wizard__back" onClick={() => setAdim(1)} type="button">
          ← Tür değiştir
        </button>
        <strong>{secili?.baslik}</strong>
      </div>

      <div className="wizard__form">
        <label htmlFor="ozel-ad">Ad</label>
        <input
          autoFocus
          id="ozel-ad"
          onChange={(event) => set({ ad: event.target.value })}
          placeholder={deger.tasima === "stdio" ? "godot" : "kendi-mcp"}
          value={deger.ad}
        />

        {deger.tasima === "stdio" && (
          <>
            <label htmlFor="ozel-komut">Komut</label>
            <input
              id="ozel-komut"
              onChange={(event) => set({ komut: event.target.value })}
              placeholder="npx -y godot-mcp"
              value={deger.komut}
            />
          </>
        )}

        {deger.tasima === "streamable_http" && (
          <>
            <label htmlFor="ozel-url">MCP adresi</label>
            <input
              id="ozel-url"
              onChange={(event) => set({ url: event.target.value })}
              placeholder="https://mcp.example.com/mcp"
              type="url"
              value={deger.url}
            />
            <label htmlFor="ozel-token">Erişim token'ı</label>
            <input
              id="ozel-token"
              onChange={(event) => set({ token: event.target.value })}
              placeholder="Varsa OAuth atlanır; giriş penceresi açılmaz"
              type="password"
              value={deger.token}
            />
            <label htmlFor="ozel-kapsam">OAuth kapsamları</label>
            <input
              id="ozel-kapsam"
              onChange={(event) => set({ kapsamlar: event.target.value })}
              placeholder="boş bırakılabilir"
              value={deger.kapsamlar}
            />
            <label htmlFor="ozel-client">Client ID</label>
            <input
              id="ozel-client"
              onChange={(event) => set({ client_id: event.target.value })}
              placeholder="Sunucu otomatik kaydı reddederse sağlayıcının verdiği kimlik"
              value={deger.client_id}
            />
            {deger.client_id.trim() && oauthDonusAdresi && (
              <p className="wizard__note">
                Kendi OAuth uygulamanı kullanıyorsun. Sağlayıcının panelinde{" "}
                <strong>geçerli yönlendirme adresi</strong> olarak tam olarak şunu kaydet:{" "}
                <code>{oauthDonusAdresi}</code>
              </p>
            )}
          </>
        )}

        {deger.tasima === "hosted" && (
          <>
            <label htmlFor="ozel-hosted-url">MCP adresi</label>
            <input
              id="ozel-hosted-url"
              onChange={(event) => set({ url: event.target.value })}
              placeholder="https://mcp.facebook.com/ads"
              type="url"
              value={deger.url}
            />
            {saglayicilar === null ? (
              <p className="wizard__note">Sağlayıcılar okunuyor…</p>
            ) : hazirSaglayici ? (
              <fieldset className="wizard__providers">
                <legend>Hangi sağlayıcı üzerinden?</legend>
                {saglayicilar.map((item) => (
                  <label className="wizard__provider" key={item.id}>
                    <input
                      checked={deger.saglayici === item.id}
                      disabled={!item.hazir}
                      name="hosted-saglayici"
                      onChange={() => set({ saglayici: item.id })}
                      type="radio"
                      value={item.id}
                    />
                    <span>
                      {item.ad}
                      {!item.hazir && <em>oturum bağlı değil</em>}
                    </span>
                  </label>
                ))}
              </fieldset>
            ) : (
              <p className="wizard__warn" role="alert">
                Hiçbir web sağlayıcısına bağlı değilsin. Bu bağlantı araçlarını bir web
                oturumu üzerinden çalıştırır; önce Kontrol Paneli'nden bir sağlayıcıya
                giriş yap.
              </p>
            )}
            <p className="wizard__note">
              Ekle'ye bastığında adres panoya kopyalanır, sağlayıcının connector ekranı
              açılır ve bağlantı kendiliğinden doğrulanır.
            </p>
          </>
        )}
      </div>

      <div className="wizard__foot">
        <Button onClick={onCancel} variant="secondary">Vazgeç</Button>
        <Button disabled={mesgul || !gonderilebilir} loading={mesgul} onClick={onSubmit} variant="primary">
          Ekle
        </Button>
      </div>
    </div>
  );
}

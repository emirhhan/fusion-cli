import { useState, type FormEvent } from "react";
import { Button } from "../ui/Button";
import { Logo } from "../brand/Logo";
import type { AccountController } from "./useAccount";
import "./account.css";

/**
 * Giriş kapısı — Fusion hesapsız açılmaz.
 *
 * İki sütun: solda form, sağda marka alanı. Sağ sütun bir GÖRSEL DOSYASI
 * taşımaz; Signal Green gradyanı ve ince bir ızgara dokusuyla çizilir. Böylece
 * pakete yeni bir varlık girmez, iki temada da aynı kalır ve yavaş diskte
 * yüklenmeyi bekleyen boş bir kutu oluşmaz.
 *
 * Hesaplar bu bilgisayardadır; sunucu yoktur. Bu ekranda AÇIKÇA yazar:
 * kullanıcı parolasını unuttuğunda "sıfırlama e-postası" beklemesin, kurtarma
 * kodunu saklaması gerektiğini baştan bilsin. Aynı sebeple sağlayıcı ile giriş
 * (Google vb.) YOKTUR: arkasında bir kimlik sunucusu olmadan çalışmaz ve
 * çalışmayan bir düğme koymak kullanıcıyı yanıltırdı.
 */

type Kip = "giris" | "kayit" | "kurtarma";

const EN_AZ_PAROLA = 8;

/** Kayıt sonrası kurtarma kodunu BİR KEZ gösteren ekran. */
function RecoveryCode({ kod, onDevam }: { kod: string; onDevam: () => void }) {
  const [kopyalandi, setKopyalandi] = useState(false);
  return (
    <div className="account">
      <section className="account__form-col">
        <div className="account__panel">
          <h1>Kurtarma kodun</h1>
          <p className="account__lead">
            Parolanı unutursan hesabına girmenin <strong>tek yolu</strong> bu koddur. Fusion
            hesapları bu bilgisayarda tutar; sıfırlama e-postası gönderebileceğimiz bir
            sunucu yok. Kodu güvenli bir yere kaydet.
          </p>
          <code className="account__recovery">{kod}</code>
          <div className="account__actions">
            <Button
              onClick={() => {
                void navigator.clipboard?.writeText(kod).then(() => setKopyalandi(true));
              }}
              variant="secondary"
            >
              {kopyalandi ? "Kopyalandı" : "Kopyala"}
            </Button>
            <Button disabled={!kopyalandi} onClick={onDevam} variant="primary">
              Kaydettim, devam et
            </Button>
          </div>
          {!kopyalandi && <p className="account__hint">Devam edebilmek için önce kodu kopyala.</p>}
        </div>
      </section>
      <BrandPanel />
    </div>
  );
}

/** Sağ sütun: dosyasız marka alanı. */
function BrandPanel() {
  return (
    <aside aria-hidden="true" className="account__brand-col">
      <div className="account__brand-glow" />
      <div className="account__brand-grid" />
      <p className="account__brand-line">
        Ücretsiz modellerle çalışan,
        <br />
        terminalde yaşayan kodlama asistanı.
      </p>
    </aside>
  );
}

export function AccountGate({ account }: { account: AccountController }) {
  const kurulum = account.durum?.kurulum_gerekli ?? false;
  const [kip, setKip] = useState<Kip>(kurulum ? "kayit" : "giris");
  const [kimlik, setKimlik] = useState("");
  const [parola, setParola] = useState("");
  const [kullaniciAdi, setKullaniciAdi] = useState("");
  const [eposta, setEposta] = useState("");
  const [kurtarmaKodu, setKurtarmaKodu] = useState("");
  const [beniHatirla, setBeniHatirla] = useState(true);
  const [yeniKod, setYeniKod] = useState<string | null>(null);
  const [bilgi, setBilgi] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState(false);

  if (yeniKod) {
    // Kod gösterildikten sonra uygulama YENİDEN YÜKLENİR: hesabın kendi
    // yapılandırması ancak yeni bir çekirdek sürecinde okunur.
    return <RecoveryCode kod={yeniKod} onDevam={() => window.location.reload()} />;
  }

  const gonder = async (event: FormEvent) => {
    event.preventDefault();
    if (mesgul) return;
    setMesgul(true);
    setBilgi(null);
    try {
      if (kip === "kayit") {
        // Avatar BURADA sorulmaz: kayıt en kısa yol olmalı. Seçimi Hesabım
        // ekranında, tıklanabilir bir seçiciyle yapılır.
        const sonuc = await account.kayit({
          kullanici_adi: kullaniciAdi,
          eposta,
          parola,
          avatar: "",
        });
        if (sonuc) setYeniKod(sonuc.kurtarma_kodu);
        return;
      }
      if (kip === "giris") {
        if (await account.giris(kimlik, parola)) window.location.reload();
        return;
      }
      if (await account.kurtar(kimlik, kurtarmaKodu, parola)) {
        setBilgi("Parola değiştirildi. Yeni parolanla giriş yapabilirsin.");
        setKip("giris");
        setParola("");
      }
    } finally {
      setMesgul(false);
    }
  };

  const baslik = kip === "kayit" ? "Kayıt Ol" : kip === "giris" ? "Giriş Yap" : "Parolanı Sıfırla";

  return (
    <div className="account">
      <section className="account__form-col">
        <form className="account__panel" onSubmit={(event) => void gonder(event)}>
          <div className="account__brand">
            <Logo size={26} />
            <span className="fusion-wordmark">Fusion</span>
          </div>
          <h1>{baslik}</h1>
          <p className="account__subtitle">Yerel hesap · bu bilgisayarda</p>

          {kip === "kayit" ? (
            <>
              <label htmlFor="hesap-ad">Kullanıcı adınız</label>
              <input
                autoFocus
                id="hesap-ad"
                onChange={(event) => setKullaniciAdi(event.target.value)}
                placeholder="Kullanıcı adınız"
                required
                value={kullaniciAdi}
              />
              <label htmlFor="hesap-eposta">E-posta adresiniz</label>
              <input
                id="hesap-eposta"
                onChange={(event) => setEposta(event.target.value)}
                placeholder="E-posta adresiniz"
                required
                type="email"
                value={eposta}
              />
            </>
          ) : (
            <>
              <label htmlFor="hesap-kimlik">E-posta adresiniz veya kullanıcı adınız</label>
              <input
                autoFocus
                id="hesap-kimlik"
                onChange={(event) => setKimlik(event.target.value)}
                placeholder="E-posta adresiniz"
                required
                value={kimlik}
              />
            </>
          )}

          {kip === "kurtarma" && (
            <>
              <label htmlFor="hesap-kod">Kurtarma kodunuz</label>
              <input
                id="hesap-kod"
                onChange={(event) => setKurtarmaKodu(event.target.value)}
                placeholder="XXXX-XXXX-XXXX-XXXX"
                required
                value={kurtarmaKodu}
              />
            </>
          )}

          <label htmlFor="hesap-parola">{kip === "kurtarma" ? "Yeni şifreniz" : "Şifreniz"}</label>
          <input
            id="hesap-parola"
            minLength={kip === "giris" ? undefined : EN_AZ_PAROLA}
            onChange={(event) => setParola(event.target.value)}
            placeholder="Şifreniz"
            required
            type="password"
            value={parola}
          />

          {kip === "giris" ? (
            <div className="account__row">
              <label className="account__check" htmlFor="hesap-hatirla">
                <input
                  checked={beniHatirla}
                  id="hesap-hatirla"
                  onChange={(event) => setBeniHatirla(event.target.checked)}
                  type="checkbox"
                />
                <span>Beni Hatırla</span>
              </label>
              <button className="account__link" onClick={() => setKip("kurtarma")} type="button">
                Şifremi Unuttum ?
              </button>
            </div>
          ) : (
            <p className="account__hint">En az {EN_AZ_PAROLA} karakter.</p>
          )}

          {account.hata && (
            <p className="account__error" role="alert">
              {account.hata}
            </p>
          )}
          {bilgi && (
            <p className="account__notice" role="status">
              {bilgi}
            </p>
          )}

          <Button disabled={mesgul} loading={mesgul} type="submit" variant="primary">
            {baslik}
          </Button>

          <p className="account__footnote">
            {kip === "kayit" ? (
              kurulum ? (
                "İlk hesabını açıyorsun."
              ) : (
                <>
                  Zaten hesabın var mı?{" "}
                  <button className="account__link" onClick={() => setKip("giris")} type="button">
                    Giriş Yap
                  </button>
                </>
              )
            ) : (
              <>
                Henüz üye değil misiniz?{" "}
                <button className="account__link" onClick={() => setKip("kayit")} type="button">
                  Kayıt Ol
                </button>
              </>
            )}
          </p>

          <p className="account__legal">
            Hesabın yalnız bu bilgisayarda tutulur. Hiçbir bilgi sunucuya gönderilmez;
            hesabı silersen ya da Fusion'ı kaldırırsan verileri de gider.
          </p>
        </form>
      </section>
      <BrandPanel />
    </div>
  );
}

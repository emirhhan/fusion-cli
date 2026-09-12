import { useState } from "react";
import { Button } from "../ui/Button";
import { PageHeader } from "../ui/PageHeader";
import { AvatarPicker, AvatarView } from "./AvatarPicker";
import type { Hesap } from "./types";
import type { AccountController } from "./useAccount";
import "./account.css";

/**
 * Hesabım ekranı — profil, hesap değiştirme ve silme.
 *
 * Silme GERİ ALINAMAZ ve ürünün sözü budur: hesap gidince ona ait ayarlar da
 * gider. Bu yüzden onay, kullanıcı adını ELLE yazdırarak alınır; tek tıkla
 * silinebilen bir şey için bu ağır, geri getirilemeyen bir şey için değil.
 */

export function AccountScreen({
  account,
  onClose,
  onPickAvatarFile,
}: {
  account: AccountController;
  onClose: () => void;
  /** Dosya seçtirip hesabın dizinine kopyalar; kaydedilen yolu döndürür. */
  onPickAvatarFile?: () => Promise<string | null>;
}) {
  const durum = account.durum;
  const etkin = durum?.hesaplar.find((item) => item.kimlik === durum.etkin) ?? null;
  const [taslak, setTaslak] = useState<Hesap | null>(etkin);
  const [silOnayi, setSilOnayi] = useState("");
  const [bilgi, setBilgi] = useState<string | null>(null);

  if (!durum || !etkin || !taslak) {
    return (
      <main className="account-screen">
        <PageHeader
          actions={<Button onClick={onClose} variant="secondary">Kapat</Button>}
          description="Hesap bilgisi okunamadı."
          eyebrow="Hesap"
          title="Hesabım"
        />
      </main>
    );
  }

  const digerHesaplar = durum.hesaplar.filter((item) => item.kimlik !== etkin.kimlik);

  return (
    <main className="account-screen">
      <PageHeader
        actions={<Button onClick={onClose} variant="secondary">Kapat</Button>}
        description="Hesabın yalnız bu bilgisayarda tutulur; hiçbir bilgi sunucuya gitmez."
        eyebrow="Hesap"
        title="Hesabım"
      />

      {account.hata && <p className="account__error" role="alert">{account.hata}</p>}
      {bilgi && <p className="account__notice" role="status">{bilgi}</p>}

      <section className="account-screen__card">
        <h3>Profil</h3>
        <div className="account-screen__identity">
          {/* Avatar TIKLANABİLİR: seçim burada yapılır, kayıt formunda değil. */}
          <AvatarPicker
            avatar={taslak.avatar}
            kullaniciAdi={taslak.kullanici_adi}
            onSelect={(avatar) => setTaslak({ ...taslak, avatar })}
            onUpload={onPickAvatarFile ?? (async () => null)}
          />
          <div>
            <strong>{etkin.kullanici_adi}</strong>
            <small>{etkin.eposta}</small>
          </div>
        </div>
        <label htmlFor="hesap-duzenle-ad">Kullanıcı adı</label>
        <input
          id="hesap-duzenle-ad"
          onChange={(event) => setTaslak({ ...taslak, kullanici_adi: event.target.value })}
          value={taslak.kullanici_adi}
        />
        <label htmlFor="hesap-duzenle-eposta">E-posta</label>
        <input
          id="hesap-duzenle-eposta"
          onChange={(event) => setTaslak({ ...taslak, eposta: event.target.value })}
          type="email"
          value={taslak.eposta}
        />
        <Button
          onClick={() => {
            void account.guncelle(taslak).then((tamam) => {
              if (tamam) setBilgi("Profil güncellendi.");
            });
          }}
          variant="primary"
        >
          Kaydet
        </Button>
      </section>

      <section className="account-screen__card">
        <h3>Hesap değiştir</h3>
        {digerHesaplar.length === 0 ? (
          <p className="account__hint">
            Bu bilgisayarda başka hesap yok. Çıkış yapıp yeni bir hesap açabilirsin.
          </p>
        ) : (
          <ul className="account-screen__list">
            {digerHesaplar.map((item) => (
              <li key={item.kimlik}>
                <span className="account-screen__avatar account-screen__avatar--small">
                  <AvatarView avatar={item.avatar} kullaniciAdi={item.kullanici_adi} />
                </span>
                <div>
                  <strong>{item.kullanici_adi}</strong>
                  <small>{item.eposta}</small>
                </div>
                {/* Geçiş çıkıştan geçer: her hesabın kendi yapılandırması var ve
                    o ancak yeni bir çekirdek sürecinde okunur. */}
                <Button
                  onClick={() => void account.cikis().then(() => window.location.reload())}
                  variant="secondary"
                >
                  Bu hesaba geç
                </Button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="account-screen__card account-screen__card--danger">
        <h3>Hesabı sil</h3>
        <p className="account__hint">
          Hesap ve ona ait ayarlar (sağlayıcı oturumları, MCP bağlantıları, model
          tercihleri) kalıcı olarak silinir. Geri alınamaz.
        </p>
        <label htmlFor="hesap-sil-onay">
          Onaylamak için kullanıcı adını yaz: <code>{etkin.kullanici_adi}</code>
        </label>
        <input
          id="hesap-sil-onay"
          onChange={(event) => setSilOnayi(event.target.value)}
          value={silOnayi}
        />
        <Button
          disabled={silOnayi !== etkin.kullanici_adi}
          onClick={() => {
            void account.sil(etkin.kimlik).then((tamam) => {
              if (tamam) window.location.reload();
            });
          }}
          variant="danger"
        >
          Hesabı kalıcı olarak sil
        </Button>
      </section>
    </main>
  );
}

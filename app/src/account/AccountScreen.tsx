import { useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
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
  client,
  onClose,
  onPickAvatarFile,
}: {
  account: AccountController;
  client?: ProtocolClient;
  onClose: () => void;
  /** Dosya seçtirip hesabın dizinine kopyalar; kaydedilen yolu döndürür. */
  onPickAvatarFile?: () => Promise<string | null>;
}) {
  const durum = account.durum;
  const etkin = durum?.hesaplar.find((item) => item.kimlik === durum.etkin) ?? null;
  const [taslak, setTaslak] = useState<Hesap | null>(etkin);
  const [silOnayi, setSilOnayi] = useState("");
  const [bilgi, setBilgi] = useState<string | null>(null);
  const [usage, setUsage] = useState<{ cagri: number; toplam_token: number } | null>(null);

  useEffect(() => {
    setTaslak(etkin);
  // Reset the edit draft when the active account changes, not during each keystroke.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [etkin?.kimlik]);

  useEffect(() => {
    if (!client) return;
    let alive = true;
    void client.request("kullanim.durum", {}).then((value) => {
      const result = value as { ok?: boolean; kullanim?: { cagri: number; toplam_token: number } };
      if (alive && result.ok && result.kullanim) setUsage(result.kullanim);
    }).catch(() => undefined);
    return () => { alive = false; };
  }, [client]);

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
      <div className="account-screen__toolbar">
        <Button onClick={onClose} variant="secondary">Kapat</Button>
      </div>

      {account.hata && <p className="account__error" role="alert">{account.hata}</p>}
      {bilgi && <p className="account__notice" role="status">{bilgi}</p>}

      <div className="account-screen__content">
      <section className="account-screen__hero" aria-label="Profil">
        <div className="account-screen__hero-avatar">
          {/* Avatar TIKLANABİLİR: seçim burada yapılır, kayıt formunda değil. */}
          <AvatarPicker
            avatar={taslak.avatar}
            kullaniciAdi={taslak.kullanici_adi}
            onSelect={(avatar) => {
              const previousAvatar = taslak.avatar;
              setTaslak({ ...taslak, avatar });
              void account.guncelle({ ...etkin, avatar }).then((tamam) => {
                if (tamam) setBilgi("Avatar güncellendi.");
                else setTaslak((current) => current ? { ...current, avatar: previousAvatar } : current);
              });
            }}
            onUpload={onPickAvatarFile ?? (async () => null)}
          />
        </div>
        <h2>{etkin.kullanici_adi}</h2>
        <p>{etkin.eposta}</p>
        <span className="account-screen__local">Bu bilgisayardaki hesap</span>
        {usage && (
          <dl className="account-screen__stats" aria-label="Bu oturumdaki kullanım">
            <div><dt>Model çağrısı</dt><dd>{usage.cagri.toLocaleString("tr-TR")}</dd></div>
            <div><dt>Token</dt><dd>{usage.toplam_token.toLocaleString("tr-TR")}</dd></div>
          </dl>
        )}
      </section>

      <details className="account-screen__section">
        <summary>Profili düzenle</summary>
        <div className="account-screen__section-body">
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
        </div>
      </details>

      <details className="account-screen__section">
        <summary>Hesap yönetimi</summary>
        <div className="account-screen__section-body">
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
                  onClick={() => void account.cikis().then((tamam) => { if (tamam) window.location.reload(); })}
                  variant="secondary"
                >
                  Bu hesaba geç
                </Button>
              </li>
            ))}
          </ul>
        )}
        </div>
      </details>

      <details className="account-screen__section account-screen__section--danger">
        <summary>Hesabı sil</summary>
        <div className="account-screen__section-body">
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
        </div>
      </details>
      </div>
    </main>
  );
}

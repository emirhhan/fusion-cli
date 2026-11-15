import { useEffect, useRef, useState } from "react";
import { Button } from "../ui/Button";
import { assetUrl } from "../platform/assetUrl";
import { hesapBasHarfleri } from "./types";
import { FUSION_AVATARLARI, VARSAYILAN_FUSION_AVATARI, fusionAvatarDegeri, fusionAvatariBul } from "./fusionAvatars";
import "./account.css";

/**
 * Avatar seçici — Fusion'ın 7 hazır avatarı ya da kullanıcının kendi görseli.
 *
 * `avatar` alanı TEK bir metindir ve şu biçimlerden birini taşır: hazır avatar
 * (`fusion:<kimlik>`), hesabın dizinine kopyalanmış görselin mutlak yolu ya da
 * (eski sürümlerden kalan) emoji. Ayrım değere bakılarak yapılır; ikinci bir alan
 * açmak şemayı ve tüm çağıranları değiştirmeyi gerektirirdi. Emoji artık
 * seçilemez; eski emoji seçimi olan hesapta varsayılan hazır avatar görünür.
 */

/** Yol ayıracı taşıyan avatar bir dosyadır; taşımayan emojidir. */
export function gorselAvatarMi(avatar: string): boolean {
  return avatar.includes("/") || avatar.includes("\\");
}


export interface AvatarPickerProps {
  avatar: string;
  kullaniciAdi: string;
  /** Seçim yapıldığında çağrılır: `fusion:<kimlik>` ya da kopyalanmış dosyanın yolu. */
  onSelect: (avatar: string) => void;
  /** Dosya seçtirip hesabın dizinine kopyalar; kaydedilen yolu döndürür. Verilmezse yükleme düğmesi çizilmez. */
  onUpload?: () => Promise<string | null>;
}

/** Avatarın kendisi — hazır avatar, yüklenen görsel ya da baş harfler. */
export function AvatarView({ avatar, kullaniciAdi }: { avatar: string; kullaniciAdi: string }) {
  const basHarfler = hesapBasHarfleri({ kullanici_adi: kullaniciAdi });
  if (!avatar) return <>{basHarfler}</>;
  const hazir = fusionAvatariBul(avatar);
  if (hazir) return <img alt="" className="account-avatar__image" data-avatar={hazir.id} src={hazir.src} />;
  if (gorselAvatarMi(avatar)) {
    const kaynak = assetUrl(avatar);
    // Kabuk yokken (test, tarayıcı) dosya adresi üretilemez; baş harfler kalır.
    return kaynak ? <img alt="" className="account-avatar__image" src={kaynak} /> : <>{basHarfler}</>;
  }
  // Eski sürümün emoji seçimi: emoji artık sunulmuyor, varsayılan hazır avatar gösterilir.
  return <img alt="" className="account-avatar__image" data-avatar={VARSAYILAN_FUSION_AVATARI.id} src={VARSAYILAN_FUSION_AVATARI.src} />;
}

export function AvatarPicker({ avatar, kullaniciAdi, onSelect, onUpload }: AvatarPickerProps) {
  const [acik, setAcik] = useState(false);
  const [mesgul, setMesgul] = useState(false);
  const [yuklemeHatasi, setYuklemeHatasi] = useState<string | null>(null);
  const kapsayici = useRef<HTMLDivElement>(null);
  const tetikleyici = useRef<HTMLButtonElement>(null);

  // Menü Escape ve dışarı tıklamayla kapanır; Escape odağı tetikleyiciye döndürür (U5-34).
  useEffect(() => {
    if (!acik) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setAcik(false);
      tetikleyici.current?.focus();
    };
    const onPointer = (event: MouseEvent) => {
      if (event.target instanceof Node && !kapsayici.current?.contains(event.target)) setAcik(false);
    };
    window.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [acik]);

  return (
    <div className="account-avatar" ref={kapsayici}>
      <button
        aria-expanded={acik}
        aria-haspopup="dialog"
        aria-label="Avatarı değiştir"
        ref={tetikleyici}
        className="account-screen__avatar account-avatar__trigger"
        onClick={() => setAcik((current) => !current)}
        type="button"
      >
        <AvatarView avatar={avatar} kullaniciAdi={kullaniciAdi} />
        <span aria-hidden="true" className="account-avatar__badge">Değiştir</span>
      </button>

      {acik && (
        <div aria-label="Avatar seçenekleri" className="account-avatar__menu" role="dialog">
          <p className="account-avatar__title">Avatar seç</p>
          <div className="account-avatar__grid">
            {FUSION_AVATARLARI.map((secenek) => {
              const deger = fusionAvatarDegeri(secenek);
              return (
                <button
                  aria-label={`Avatar: ${secenek.ad}`}
                  aria-pressed={avatar === deger}
                  className="account-avatar__option"
                  key={secenek.id}
                  onClick={() => {
                    onSelect(deger);
                    setAcik(false);
                  }}
                  title={secenek.ad}
                  type="button"
                >
                  <img alt="" src={secenek.src} />
                </button>
              );
            })}
          </div>
          {(onUpload || avatar) && <div className="account-avatar__foot">
            {onUpload && (
              <Button
                loading={mesgul}
                onClick={() => {
                  setMesgul(true);
                  setYuklemeHatasi(null);
                  // Kopyalama hatası işlenmemiş reddedilme olmaz, kullanıcıya gösterilir (U5-34).
                  void onUpload()
                    .then((yol) => {
                      if (yol) {
                        onSelect(yol);
                        setAcik(false);
                      }
                    })
                    .catch(() => setYuklemeHatasi("Görsel yüklenemedi. Başka bir dosya dene."))
                    .finally(() => setMesgul(false));
                }}
                variant="secondary"
              >
                Görsel yükle
              </Button>
            )}
            {yuklemeHatasi && <p className="account__error" role="alert">{yuklemeHatasi}</p>}
            {avatar && (
              <button
                className="account__link"
                onClick={() => {
                  onSelect("");
                  setAcik(false);
                }}
                type="button"
              >
                Kaldır
              </button>
            )}
          </div>}
        </div>
      )}
    </div>
  );
}

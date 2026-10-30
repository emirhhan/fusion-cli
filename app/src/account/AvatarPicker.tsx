import { useEffect, useRef, useState } from "react";
import { Button } from "../ui/Button";
import { assetUrl } from "../platform/assetUrl";
import { hesapBasHarfleri } from "./types";
import "./account.css";

/**
 * Avatar seçici — emoji ızgarası ya da kullanıcının kendi görseli.
 *
 * `avatar` alanı TEK bir metindir ve iki biçimden birini taşır: emoji ya da
 * hesabın dizinine kopyalanmış görselin mutlak yolu. Ayrım yol ayıracına
 * bakılarak yapılır; ikinci bir alan açmak şemayı ve tüm çağıranları
 * değiştirmeyi gerektirirdi.
 */

/** Yol ayıracı taşıyan avatar bir dosyadır; taşımayan emojidir. */
export function gorselAvatarMi(avatar: string): boolean {
  return avatar.includes("/") || avatar.includes("\\");
}

/** Kısa, ürünle uyumlu bir emoji seti. Tam emoji klavyesi burada gereksiz. */
const EMOJILER = [
  "🏍️", "🛵", "🏁", "⚙️", "🔧", "🛠️",
  "🚀", "⚡", "🔥", "💡", "🎯", "🧠",
  "🐺", "🦊", "🐙", "🦉", "🐉", "🦅",
  "🎮", "🎧", "🎸", "📷", "☕", "🌙",
] as const;

export interface AvatarPickerProps {
  avatar: string;
  kullaniciAdi: string;
  /** Seçim yapıldığında çağrılır: emoji ya da kopyalanmış dosyanın yolu. */
  onSelect: (avatar: string) => void;
  /** Dosya seçtirip hesabın dizinine kopyalar; kaydedilen yolu döndürür. Verilmezse yükleme düğmesi çizilmez. */
  onUpload?: () => Promise<string | null>;
}

/** Avatarın kendisi — görsel, emoji ya da baş harfler. */
export function AvatarView({ avatar, kullaniciAdi }: { avatar: string; kullaniciAdi: string }) {
  const kaynak = gorselAvatarMi(avatar) ? assetUrl(avatar) : null;
  if (kaynak) return <img alt="" className="account-avatar__image" src={kaynak} />;
  // Kabuk yokken (test, tarayıcı) dosya adresi üretilemez; baş harfler kalır.
  if (gorselAvatarMi(avatar)) return <>{hesapBasHarfleri({ kullanici_adi: kullaniciAdi })}</>;
  return <>{avatar || hesapBasHarfleri({ kullanici_adi: kullaniciAdi })}</>;
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
          <div className="account-avatar__grid">
            {EMOJILER.map((emoji) => (
              <button
                aria-label={`Avatar: ${emoji}`}
                aria-pressed={avatar === emoji}
                className="account-avatar__option"
                key={emoji}
                onClick={() => {
                  onSelect(emoji);
                  setAcik(false);
                }}
                type="button"
              >
                {emoji}
              </button>
            ))}
          </div>
          <div className="account-avatar__foot">
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
          </div>
        </div>
      )}
    </div>
  );
}

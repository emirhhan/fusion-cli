import { useEffect, useRef, useState } from "react";
import { Icon } from "../ui/Icon";
import "./ModelPicker.css";

/**
 * Composer'ın sağındaki model seçici.
 *
 * Hangi modelle konuştuğu kullanıcıya HİÇBİR YERDE yazmıyordu: model ancak
 * Kontrol Paneli açılıp "Model düzeni" okunarak görülebiliyordu. Seçici adı
 * görünür kılar ve değiştirmeyi bir tıka indirir.
 *
 * Liste ÇEKİRDEKTEN gelir ve seçim `/model` komutuyla uygulanır; burada ikinci
 * bir model yönetimi yolu açılmaz (RULES: "aynı işi yapan ikinci bir yol
 * açılmaz"). Bileşen ağı bilmez, veriyi props ile alır — testte gerçek oturum
 * gerekmesin.
 */

export interface ModelOption {
  /** `/model` komutuna verilecek devam değeri. */
  deger: string;
  etiket: string;
  aciklama?: string;
}

export interface ModelPickerProps {
  /** Etkin ajan modeli; liste açılmadan da görünür. */
  active: string;
  options: ModelOption[];
  /** Liste açılırken çağrılır; seçenekler tembel yüklenir. */
  onOpen?: () => void;
  onSelect: (deger: string) => void;
  busy?: boolean;
}

/** Uzun model kimliğini düğmeye sığacak biçimde kısalt: sağlayıcı önekini at. */
export function shortModelName(model: string): string {
  if (!model) return "Model seç";
  const parcalar = model.split("/");
  return parcalar[parcalar.length - 1] || model;
}

export function ModelPicker({ active, busy = false, onOpen, onSelect, options }: ModelPickerProps) {
  const [open, setOpen] = useState(false);
  const kutu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const disariTikla = (event: MouseEvent) => {
      if (!kutu.current?.contains(event.target as Node)) setOpen(false);
    };
    const kacisTusu = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", disariTikla);
    document.addEventListener("keydown", kacisTusu);
    return () => {
      document.removeEventListener("mousedown", disariTikla);
      document.removeEventListener("keydown", kacisTusu);
    };
  }, [open]);

  const ac = () => {
    setOpen((current) => {
      if (!current) onOpen?.();
      return !current;
    });
  };

  return (
    <div className="model-picker" ref={kutu}>
      <button
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={`Model: ${active || "seçilmedi"}. Değiştirmek için tıkla.`}
        className="model-picker__trigger"
        onClick={ac}
        title={active}
        type="button"
      >
        <span className="model-picker__name">{shortModelName(active)}</span>
        <Icon name="chevron" size={14} />
      </button>
      {open && (
        <div aria-label="Model listesi" className="model-picker__menu" role="listbox">
          {busy && <p className="model-picker__state">Modeller okunuyor…</p>}
          {!busy && options.length === 0 && (
            <p className="model-picker__state">
              Seçilebilir model yok. Ayarlar'dan bir sağlayıcıya bağlan.
            </p>
          )}
          {options.map((option) => (
            <button
              aria-selected={option.etiket === active || option.deger === active}
              className="model-picker__option"
              key={option.deger}
              onClick={() => {
                setOpen(false);
                onSelect(option.deger);
              }}
              role="option"
              type="button"
            >
              <strong>{option.etiket}</strong>
              {option.aciklama && <small>{option.aciklama}</small>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

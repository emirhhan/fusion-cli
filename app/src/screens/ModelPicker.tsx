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
  grup?: string;
  modelId?: string;
}

export interface ModelPickerProps {
  /** Etkin ajan modeli; liste açılmadan da görünür. */
  active: string;
  activeLabel?: string;
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

export function ModelPicker({ active, activeLabel, busy = false, onOpen, onSelect, options }: ModelPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const kutu = useRef<HTMLDivElement>(null);
  const groupLabels: Record<string, string> = {
    low: "Basit ve hızlı görevler",
    medium: "Orta düzey görevler",
    high: "Büyük ve karmaşık görevler",
    ultra: "Derin araştırma ve geliştirme",
    premium: "En güçlü modeller",
    web: "Bağlı web oturumları",
    diger: "Diğer etkin modeller",
  };
  const visible = options.filter((option) =>
    `${option.etiket} ${option.aciklama ?? ""} ${option.deger}`
      .toLocaleLowerCase("tr").includes(query.trim().toLocaleLowerCase("tr")),
  );
  const grouped = new Map<string, ModelOption[]>();
  for (const option of visible) {
    const group = option.grup ?? "diger";
    grouped.set(group, [...(grouped.get(group) ?? []), option]);
  }
  const groups = [...grouped.entries()];

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
      if (!current) {
        setQuery("");
        onOpen?.();
      }
      return !current;
    });
  };

  return (
    <div className="model-picker" ref={kutu}>
      <button
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={`Model: ${activeLabel || active || "seçilmedi"}. Değiştirmek için tıkla.`}
        className="model-picker__trigger"
        onClick={ac}
        title={activeLabel || active}
        type="button"
      >
        <span className="model-picker__name">{activeLabel || shortModelName(active)}</span>
        <Icon name="chevron" size={14} />
      </button>
      {open && (
        <div aria-label="Model listesi" className="model-picker__menu" role="listbox">
          <input
            aria-label="Model ara"
            className="model-picker__search"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Model ara"
            type="search"
            value={query}
          />
          {busy && <p className="model-picker__state">Modeller okunuyor…</p>}
          {!busy && options.length === 0 && (
            <p className="model-picker__state">
              Seçilebilir model yok. Ayarlar'dan bir sağlayıcıya bağlan.
            </p>
          )}
          {!busy && options.length > 0 && visible.length === 0 && (
            <p className="model-picker__state">Aramayla eşleşen etkin model yok.</p>
          )}
          {!busy && groups.map(([group, entries]) => (
            <div className="model-picker__group" key={group} role="presentation">
              <p className="model-picker__group-title">{groupLabels[group] ?? group}</p>
              {entries?.map((option) => (
                <button
                  aria-selected={option.modelId === active || option.deger === active}
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
          ))}
        </div>
      )}
    </div>
  );
}

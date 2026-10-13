import { useEffect, useId, useRef, useState } from "react";
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
  const ad = parcalar[parcalar.length - 1] || model;
  // Çipte "nemotron-3-ultra-550b-a55b:free" yerine "nemotron-3-ultra": parametre
  // boyutu (550b, a55b) ve ":free" eki yazma kutusunun yerini boşuna yiyordu.
  return ad.replace(/:free$/, "").replace(/-\d+(?:\.\d+)?b-a\d+(?:\.\d+)?b(?=-|$)/gi, "") || ad;
}

export function ModelPicker({ active, activeLabel, busy = false, onOpen, onSelect, options }: ModelPickerProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [highlight, setHighlight] = useState(0);
  const listId = useId();
  const search = useRef<HTMLInputElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
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
    search.current?.focus();
    const disariTikla = (event: MouseEvent) => {
      if (!kutu.current?.contains(event.target as Node)) setOpen(false);
    };
    const kacisTusu = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setOpen(false); trigger.current?.focus(); }
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
        setHighlight(0);
        onOpen?.();
      }
      return !current;
    });
  };

  const keyboard = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Escape") {
      event.preventDefault(); setOpen(false); trigger.current?.focus();
      return;
    }
    if (busy || !visible.length) return;
    if (event.key === "ArrowDown") {
      event.preventDefault(); setHighlight((value) => (value + 1) % visible.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault(); setHighlight((value) => (value + visible.length - 1) % visible.length);
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault(); setHighlight(event.key === "Home" ? 0 : visible.length - 1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      const target = visible[Math.min(highlight, visible.length - 1)];
      if (target) { setOpen(false); trigger.current?.focus(); onSelect(target.deger); }
    }
  };

  return (
    <div className="model-picker" ref={kutu}>
      <button
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={`Model: ${activeLabel || active || "seçilmedi"}. Değiştirmek için tıkla.`}
        className="model-picker__trigger"
        ref={trigger}
        onClick={ac}
        title={activeLabel || active}
        type="button"
      >
        <span className="model-picker__name">{activeLabel || shortModelName(active)}</span>
        <Icon name="chevron" size={14} />
      </button>
      {open && (
        <div className="model-picker__menu">
          <input
            aria-label="Model ara"
            aria-controls={listId}
            aria-expanded={open}
            aria-autocomplete="list"
            aria-activedescendant={visible.length ? `${listId}-${Math.min(highlight, visible.length - 1)}` : undefined}
            role="combobox"
            ref={search}
            onKeyDown={keyboard}
            className="model-picker__search"
            onChange={(event) => { setQuery(event.target.value); setHighlight(0); }}
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
          <div id={listId} role="listbox" aria-label="Model listesi">
          {!busy && groups.map(([group, entries]) => (
            <div className="model-picker__group" key={group} role="group" aria-label={groupLabels[group] ?? group}>
              <p className="model-picker__group-title">{groupLabels[group] ?? group}</p>
              {entries?.map((option) => (
                <button
                  aria-selected={option.modelId === active || option.deger === active}
                  id={`${listId}-${visible.indexOf(option)}`}
                  tabIndex={-1}
                  data-highlighted={visible.indexOf(option) === highlight}
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
        </div>
      )}
    </div>
  );
}

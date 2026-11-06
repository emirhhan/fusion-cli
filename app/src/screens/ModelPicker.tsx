import { useEffect, useId, useRef, useState } from "react";
import { Icon } from "../ui/Icon";
import { approveModel, isModelApproved } from "./modelApprovals";
import "./ModelPicker.css";

/**
 * Composer'ın sağındaki model seçici.
 *
 * Hangi modelle konuştuğu kullanıcıya HİÇBİR YERDE yazmıyordu: model ancak
 * Kontrol Paneli açılıp "Model düzeni" okunarak görülebiliyordu. Seçici adı
 * görünür kılar ve değiştirmeyi bir tıka indirir.
 *
 * Liste ÇEKİRDEKTEN gelir ve seçim yapısal `model.sec {kaynak, model}` ile uygulanır
 * (komut dizgesi kurulmaz, U1-40); burada ikinci
 * bir model yönetimi yolu açılmaz (RULES: "aynı işi yapan ikinci bir yol
 * açılmaz"). Bileşen ağı bilmez, veriyi props ile alır — testte gerçek oturum
 * gerekmesin.
 */

export interface ModelOption {
  /** Seçeneğin kararlı kimliği (onay anahtarı); komut olarak ÇALIŞTIRILMAZ. */
  deger: string;
  /** Model kaynağı; `modelId` ile birlikte yapısal `model.sec {kaynak, model}` isteğini kurar (U1-40). */
  kaynak?: string;
  etiket: string;
  aciklama?: string;
  grup?: string;
  modelId?: string;
  toolSupport?: string;
  health?: string;
}

export interface ModelPickerProps {
  /** Etkin ajan modeli; liste açılmadan da görünür. */
  active: string;
  activeLabel?: string;
  activePending?: boolean;
  activeError?: string;
  onActiveRetry?: () => void;
  options: ModelOption[];
  /** Liste açılırken çağrılır; seçenekler tembel yüklenir. */
  onOpen?: () => void;
  onSelect: (option: ModelOption) => void;
  busy?: boolean;
  error?: string;
  onRetry?: () => void;
  onConnect?: () => void;
  pending?: boolean;
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

export function ModelPicker({ active, activeLabel, activePending = false, activeError = "", onActiveRetry, busy = false, onOpen, onSelect, options, error, onRetry, onConnect, pending = false }: ModelPickerProps) {
  const modelName = activeLabel || (active ? shortModelName(active) : "");
  const activeName = activePending ? `${modelName ? `${modelName} · ` : ""}Etkin model okunuyor…`
    : activeError ? (modelName ? `${modelName} · yenilenemedi` : "Etkin model okunamadı") : modelName;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const listId = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const [highlight, setHighlight] = useState(0);
  // Araç desteği doğrulanmamış modeller satır içi onayla seçilir (U1-45).
  const [confirming, setConfirming] = useState<ModelOption | null>(null);
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
    `${option.etiket} ${option.aciklama ?? ""} ${option.modelId ?? option.deger}`
      .toLocaleLowerCase("tr").includes(query.trim().toLocaleLowerCase("tr")),
  );
  const grouped = new Map<string, ModelOption[]>();
  for (const option of visible) {
    const group = option.grup ?? "diger";
    grouped.set(group, [...(grouped.get(group) ?? []), option]);
  }
  const groups = [...grouped.entries()];
  // Satır başına `visible.indexOf` yüzlerce modelde O(n²) idi (U1-43).
  const visibleIndex = new Map(visible.map((option, index) => [option, index] as const));

  useEffect(() => {
    if (!open || busy) return;
    document.getElementById(`${listId}-${Math.min(highlight, visible.length - 1)}`)
      ?.scrollIntoView?.({ block: "nearest" });
  }, [open, busy, listId, highlight, query, options, visible.length]);

  useEffect(() => {
    if (!open) return;
    search.current?.focus();
    const disariTikla = (event: MouseEvent) => {
      if (!kutu.current?.contains(event.target as Node)) setOpen(false);
    };
    const kacisTusu = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setOpen(false); trigger.current?.focus(); }
    };
    document.addEventListener("mousedown", disariTikla);
    document.addEventListener("keydown", kacisTusu);
    return () => {
      document.removeEventListener("mousedown", disariTikla);
      document.removeEventListener("keydown", kacisTusu);
    };
  }, [open]);

  const ac = () => {
    if (open) { setOpen(false); return; }
    setQuery("");
    setHighlight(0);
    setConfirming(null);
    setOpen(true);
    onOpen?.();
  };
  const acRef = useRef(ac);
  acRef.current = ac;

  useEffect(() => {
    // Cmd/Ctrl+Shift+I model menüsünü açar/kapatır (Claude Code Desktop, #444).
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || !(event.metaKey || event.ctrlKey) || !event.shiftKey || event.altKey) return;
      if (event.code !== "KeyI" && event.key.toLowerCase() !== "i") return;
      event.preventDefault();
      acRef.current();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const choose = (option: ModelOption, confirmed = false) => {
    if (pending) return;
    const approvalKey = `model-picker:${option.deger}`;
    if (option.toolSupport === "unknown" && !confirmed && !isModelApproved(approvalKey)) {
      setConfirming(option);
      return;
    }
    if (confirmed) approveModel(approvalKey);
    setConfirming(null);
    setOpen(false);
    trigger.current?.focus();
    onSelect(option);
  };
  const keyboard = (event: React.KeyboardEvent) => {
    if (!visible.length || pending || busy || confirming) return;
    let next = highlight;
    if (event.key === "ArrowDown") next = Math.min(highlight + 1, visible.length - 1);
    else if (event.key === "ArrowUp") next = Math.max(highlight - 1, 0);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = visible.length - 1;
    else if (event.key === "Enter") { event.preventDefault(); choose(visible[Math.min(highlight, visible.length - 1)]); return; }
    else return;
    event.preventDefault();
    setHighlight(next);
  };

  return (
    <div className="model-picker" ref={kutu}>
      <button
        ref={trigger}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-label={`Model: ${(activePending || activeError ? activeName : activeLabel || active) || "seçilmedi"}. Değiştirmek için tıkla.`}
        aria-busy={activePending || undefined}
        className="model-picker__trigger"
        onClick={ac}
        title={activeError || activeLabel || active}
        type="button"
      >
        <span className="model-picker__name">{activeName || shortModelName(active)}</span>
        <Icon name="chevron" size={14} />
      </button>
      {open && (
        <div className="model-picker__menu">
          <input
            ref={search}
            role="combobox"
            aria-expanded={open}
            aria-autocomplete="list"
            aria-label="Model ara"
            aria-controls={listId}
            aria-activedescendant={!busy && visible.length ? `${listId}-${Math.min(highlight, visible.length - 1)}` : undefined}
            className="model-picker__search"
            onKeyDown={keyboard}
            onChange={(event) => { setQuery(event.target.value); setHighlight(0); }}
            placeholder="Model ara"
            type="search"
            value={query}
          />
          {activeError && <p role="alert">{activeError}{onActiveRetry && <button type="button" onClick={onActiveRetry}>Etkin modeli yeniden oku</button>}</p>}
          {error && <p role="alert">{error}{onRetry && <button type="button" onClick={onRetry}>Yeniden dene</button>}</p>}
          {busy && <p className="model-picker__state">Modeller okunuyor…</p>}
          {!busy && !error && options.length === 0 && (
            <p className="model-picker__state">
              Seçilebilir model yok. Ayarlar'dan bir sağlayıcıya bağlan.
              {onConnect && <button type="button" onClick={onConnect}>Sağlayıcıya bağlan</button>}
            </p>
          )}
          {!busy && options.length > 0 && visible.length === 0 && (
            <p className="model-picker__state">Aramayla eşleşen etkin model yok.</p>
          )}
          {confirming && (
            <div className="model-picker__confirm" role="alertdialog" aria-label={`${confirming.etiket} seçimini onayla`}>
              <p><strong>{confirming.etiket}</strong> için araç desteği doğrulanmadı. Dosya ve komut araçları çalışmayabilir.</p>
              <div className="model-picker__confirm-actions">
                <button autoFocus type="button" onClick={() => setConfirming(null)}>Vazgeç</button>
                <button type="button" onClick={() => choose(confirming, true)}>Yine de seç</button>
              </div>
              <small>Seçersen bu oturumda tekrar sorulmaz.</small>
            </div>
          )}
          <div id={listId} role="listbox" aria-label="Model listesi" hidden={confirming !== null}>
          {!busy && groups.map(([group, entries]) => (
            <div className="model-picker__group" key={group} role="group" aria-labelledby={`${listId}-group-${group}`}>
              <p id={`${listId}-group-${group}`} className="model-picker__group-title">{groupLabels[group] ?? group}</p>
              {entries?.map((option) => (
                <button
                  id={`${listId}-${visibleIndex.get(option)}`}
                  disabled={pending}
                  tabIndex={-1}
                  aria-selected={option.modelId === active || option.deger === active}
                  className={`model-picker__option${visibleIndex.get(option) === Math.min(highlight, visible.length - 1) ? " model-picker__option--active" : ""}`}
                  key={option.deger}
                  onClick={() => choose(option)}
                  role="option"
                  type="button"
                >
                  <strong>{option.etiket}</strong>
                  {option.aciklama && <small>{option.aciklama}</small>}
                  {option.toolSupport === "unknown" && <small>Araç desteği doğrulanmadı</small>}
                  {option.health === "bilinmiyor" && <small>Sağlık doğrulanmadı</small>}
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

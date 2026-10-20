import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { selectDirectory } from "../platform/dialog";
import { Icon } from "../ui/Icon";
import { DAY_LABELS, describeSchedule, formatMoment, type ScheduleClient, type ScheduleKind, type ScheduledTask } from "./types";
import { SCHEDULE_TEMPLATES, type ScheduleTemplate } from "./templates";
import "./ScheduleScreen.css";

interface ScheduleScreenProps {
  /** Çekirdek bağlı değilken (hiç sohbet açılmadı) `null`. */
  client: ScheduleClient | null;
  /** Yeni görevin varsayılan çalışma klasörü: açık projenin kökü. */
  defaultRoot: string;
  chooseFolder?: (current?: string) => Promise<string | null>;
  onRunNow: (task: ScheduledTask) => Promise<void>;
  visible?: boolean;
}

interface Draft {
  baslik: string;
  dakika: string;
  gorev: string;
  gunler: number[];
  kok: string;
  saat: string;
  tarih: string;
  tur: ScheduleKind;
}

const KIND_LABEL: Record<ScheduleKind, string> = {
  bir_kez: "Bir kez",
  gunluk: "Her gün",
  haftalik: "Haftanın günleri",
  aralik: "Belirli aralıkla",
};

type Tab = "mine" | "templates";
type Filter = "all" | "active" | "paused";
type Sort = "next" | "name" | "last";

const FILTER_LABEL: Record<Filter, string> = { all: "Tümü", active: "Etkin", paused: "Duraklatılan" };
const SORT_LABEL: Record<Sort, string> = { next: "Sıradaki zamana göre", name: "Ada göre", last: "Son çalışmaya göre" };

function draftFromTemplate(template: ScheduleTemplate, root: string): Draft {
  return {
    ...emptyDraft(root),
    baslik: template.baslik,
    gorev: template.gorev,
    gunler: template.gunler ?? [0],
    saat: template.saat,
    tur: template.tur,
  };
}

function emptyDraft(root: string): Draft {
  return { baslik: "", dakika: "60", gorev: "", gunler: [0], kok: root, saat: "09:00", tarih: "", tur: "gunluk" };
}

/** Taslağı çekirdeğin beklediği alanlara çevir; eksik zamanı Türkçe hata olarak döndür. */
export function draftPayload(draft: Draft): Record<string, unknown> | string {
  const base = { baslik: draft.baslik, gorev: draft.gorev, kok: draft.kok, tur: draft.tur };
  if (draft.tur === "gunluk") return { ...base, saat: draft.saat };
  if (draft.tur === "haftalik") return { ...base, saat: draft.saat, gunler: draft.gunler };
  if (draft.tur === "aralik") return { ...base, dakika: Number.parseInt(draft.dakika, 10) };
  const moment = new Date(`${draft.tarih}T${draft.saat}`).getTime();
  if (!draft.tarih || Number.isNaN(moment)) return "Tek seferlik görev için tarih ve saat seç.";
  return { ...base, zaman: Math.floor(moment / 1000) };
}

export function ScheduleScreen({ client, defaultRoot, chooseFolder = selectDirectory, onRunNow, visible = true }: ScheduleScreenProps) {
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!client) return;
    try {
      const result = await client.request("zamanlama.liste", {});
      if (result.ok && Array.isArray(result.gorevler)) setTasks(result.gorevler as ScheduledTask[]);
    } catch {
      setError("Zamanlananlar okunamadı. Yeniden dene.");
    }
  }, [client]);

  useEffect(() => {
    if (visible) void load();
  }, [load, visible]);

  const call = async (name: string, data: Record<string, unknown>, fallback: string) => {
    if (!client) return false;
    try {
      const result = await client.request(name, data);
      if (result.ok) {
        setError(null);
        await load();
        return true;
      }
      setError(typeof result.metin === "string" ? result.metin : fallback);
    } catch {
      setError(fallback);
    }
    return false;
  };

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!draft) return;
    const payload = draftPayload(draft);
    if (typeof payload === "string") {
      setError(payload);
      return;
    }
    if (await call("zamanlama.kaydet", payload, "Görev kaydedilemedi.")) setDraft(null);
  };

  const runNow = async (task: ScheduledTask) => {
    if (await call("zamanlama.simdi", { id: task.id }, "Görev başlatılamadı.")) await onRunNow(task);
  };

  const update = (patch: Partial<Draft>) => setDraft((current) => (current ? { ...current, ...patch } : current));
  const toggleDay = (day: number) =>
    update({ gunler: draft?.gunler.includes(day) ? draft.gunler.filter((item) => item !== day) : [...(draft?.gunler ?? []), day] });

  const folderName = (path: string) => path.split(/[\\/]/).filter(Boolean).pop() ?? path;
  const [tab, setTab] = useState<Tab>("mine");
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [sort, setSort] = useState<Sort>("next");
  const [menu, setMenu] = useState<"filter" | "sort" | null>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);

  const openDraft = (next?: Draft) => { setError(null); setDraft(next ?? emptyDraft(defaultRoot)); };
  const applyTemplate = (template: ScheduleTemplate) => openDraft(draftFromTemplate(template, defaultRoot));

  const visibleTasks = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("tr");
    const isActive = (task: ScheduledTask) => task.etkin && task.sonraki !== null;
    const list = tasks.filter((task) => {
      if (filter === "active" && !isActive(task)) return false;
      if (filter === "paused" && isActive(task)) return false;
      return !needle || `${task.baslik} ${task.gorev}`.toLocaleLowerCase("tr").includes(needle);
    });
    const byNext = (task: ScheduledTask) => task.sonraki ?? Number.POSITIVE_INFINITY;
    return [...list].sort((left, right) => {
      if (sort === "name") return left.baslik.localeCompare(right.baslik, "tr");
      if (sort === "last") return (right.son_calisma ?? 0) - (left.son_calisma ?? 0);
      // Etkin görevler önde (en yakın zaman en üstte); duraklatılanlar sonda.
      if (isActive(left) !== isActive(right)) return isActive(left) ? -1 : 1;
      return byNext(left) - byNext(right);
    });
  }, [tasks, query, filter, sort]);

  useEffect(() => {
    if (!draft && menu === null) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (menu !== null) setMenu(null);
      else setDraft(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [draft, menu]);

  useEffect(() => {
    if (menu === null) return;
    const onDown = (event: MouseEvent) => {
      if (!toolbarRef.current?.contains(event.target as Node)) setMenu(null);
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [menu]);

  const templateGrid = (
    <ul aria-label="Şablonlar" className="schedule__grid">
      {SCHEDULE_TEMPLATES.map((template) => (
        <li key={template.id}>
          <button className="schedule__card schedule__card--template" onClick={() => applyTemplate(template)} type="button">
            <span aria-hidden="true" className="schedule__tile"><Icon name={template.simge} size={20} /></span>
            <span className="schedule__card-body">
              <strong className="schedule__title">{template.baslik}</strong>
              <span className="schedule__prompt">{template.aciklama}</span>
              <span className="schedule__when"><Icon name="clock" size={14} /> {describeSchedule(template)}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );

  return (
    <div className="schedule">
      <aside aria-label="Zamanlananlar menüsü" className="schedule__sidebar">
      <header className="schedule__header" data-tauri-drag-region>
        <h1>Zamanlananlar</h1>

      </header>

      <div className="schedule__toolbar" ref={toolbarRef}>
        <div aria-label="Zamanlananlar bölümleri" className="schedule__tabs" role="tablist">
          <button aria-selected={tab === "mine"} className="schedule__tab" onClick={() => setTab("mine")} role="tab" type="button">Görevlerim</button>
          <button aria-selected={tab === "templates"} className="schedule__tab" onClick={() => setTab("templates")} role="tab" type="button">Şablonlar</button>
        </div>
        <div className="schedule__tools">
          {searchOpen && (
            <input
              aria-label="Görevlerde ara"
              autoFocus
              className="schedule__search"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Ara…"
              value={query}
            />
          )}
          <button
            aria-label="Ara"
            aria-pressed={searchOpen}
            className="schedule__tool"
            onClick={() => { setSearchOpen((open) => !open); if (searchOpen) setQuery(""); }}
            title="Ara"
            type="button"
          >
            <Icon name="search" size={17} />
          </button>
          <div className="schedule__menu-wrap">
            <button
              aria-expanded={menu === "filter"}
              aria-haspopup="menu"
              aria-label="Süz"
              className="schedule__tool"
              data-active={filter !== "all"}
              onClick={() => setMenu(menu === "filter" ? null : "filter")}
              title="Süz"
              type="button"
            >
              <Icon name="filter" size={17} />
            </button>
            {menu === "filter" && (
              <div aria-label="Süz" className="schedule__menu" role="menu">
                {(Object.keys(FILTER_LABEL) as Filter[]).map((key) => (
                  <button aria-checked={filter === key} key={key} onClick={() => { setFilter(key); setMenu(null); }} role="menuitemradio" type="button">
                    {FILTER_LABEL[key]}
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="schedule__menu-wrap">
            <button
              aria-expanded={menu === "sort"}
              aria-haspopup="menu"
              aria-label="Sırala"
              className="schedule__tool"
              onClick={() => setMenu(menu === "sort" ? null : "sort")}
              title="Sırala"
              type="button"
            >
              <Icon name="sort" size={17} />
            </button>
            {menu === "sort" && (
              <div aria-label="Sırala" className="schedule__menu" role="menu">
                {(Object.keys(SORT_LABEL) as Sort[]).map((key) => (
                  <button aria-checked={sort === key} key={key} onClick={() => { setSort(key); setMenu(null); }} role="menuitemradio" type="button">
                    {SORT_LABEL[key]}
                  </button>
                ))}
              </div>
            )}
          </div>
          <button className="schedule__primary" disabled={!client} onClick={() => openDraft()} type="button">
            <Icon name="new" size={16} /> Yeni görev
          </button>
        </div>
      </div>

      <div className="schedule__upcoming">
        <h2>Yaklaşanlar</h2>
        {visibleTasks.length ? <ul aria-label="Görev menüsü">
          {visibleTasks.map((task) => <li key={task.id}><button type="button" onClick={() => {
            setTab("mine");
            requestAnimationFrame(() => {
              const card = document.getElementById(`scheduled-task-${task.id}`);
              card?.scrollIntoView({ block: "nearest" });
              card?.focus({ preventScroll: true });
            });
          }}><Icon name="clock" size={14} /><span>{task.baslik}</span></button></li>)}
        </ul> : <p className="schedule__hint">{tasks.length ? "Görev bulunamadı." : "Henüz zamanlanmış görev yok."}</p>}
      </div>
      </aside>
      <div className="schedule__content">
      <p className="schedule__hint">Görevler Fusion açıkken çalışır; her çalışma yeni bir sohbet açar.</p>

      {error && !draft && <p className="schedule__error" role="alert">{error}</p>}

      {tab === "templates" ? templateGrid : !client ? (
        <p className="schedule__empty">Zamanlananları görmek için Home'da bir sohbet aç.</p>
      ) : tasks.length === 0 ? (
        <>
          <div className="schedule__empty-state">
            <StopwatchArt />
            <p className="schedule__empty-title">Henüz zamanlanmış görev yok.</p>
            <button className="schedule__primary" onClick={() => openDraft()} type="button">İlk görevini oluştur</button>
          </div>
          <hr aria-hidden="true" className="schedule__divider" />
          {templateGrid}
        </>
      ) : visibleTasks.length === 0 ? (
        <p className="schedule__empty">Aramana ya da süzgecine uyan görev yok.</p>
      ) : (
        <ul aria-label="Zamanlanmış görevler" className="schedule__grid">
          {visibleTasks.map((task) => (
            <li className="schedule__card" data-enabled={task.etkin} id={`scheduled-task-${task.id}`} tabIndex={-1} key={task.id}>
              <span aria-hidden="true" className="schedule__tile"><Icon name="clock" size={20} /></span>
              <div className="schedule__card-body">
                <p className="schedule__title">{task.baslik}</p>
                {task.gorev && task.gorev !== task.baslik && <p className="schedule__prompt">{task.gorev}</p>}
                <p className="schedule__when">
                  <Icon name="clock" size={14} />
                  <span>{describeSchedule(task)}</span>
                  <span className="schedule__dot" aria-hidden="true">·</span>
                  <span data-tone={task.etkin && task.sonraki ? "next" : "muted"}>
                    {task.etkin && task.sonraki ? `Sıradaki ${formatMoment(task.sonraki)}` : task.sonraki ? "Duraklatıldı" : "Tamamlandı"}
                  </span>
                </p>
                <p className="schedule__meta" title={task.kok}>
                  <Icon name="folder" size={12} /> <span>{folderName(task.kok)}</span>
                  {task.son_calisma ? <> · Son çalışma {formatMoment(task.son_calisma)}{task.son_gecikmeli ? " (gecikmeli: Fusion kapalıydı)" : ""}</> : null}
                </p>
              </div>
              <div className="schedule__actions">
                <button aria-label="Şimdi çalıştır" className="schedule__icon-button" onClick={() => void runNow(task)} title="Şimdi çalıştır" type="button">
                  <Icon name="play" size={15} />
                </button>
                {task.sonraki !== null && (
                  <button
                    aria-checked={task.etkin}
                    aria-label={task.etkin ? "Duraklat" : "Sürdür"}
                    className="schedule__switch"
                    onClick={() => void call("zamanlama.etkin", { id: task.id, etkin: !task.etkin }, "Görev güncellenemedi.")}
                    role="switch"
                    title={task.etkin ? "Duraklat" : "Sürdür"}
                    type="button"
                  >
                    <span />
                  </button>
                )}
                <button
                  aria-label={`${task.baslik} görevini sil`}
                  className="schedule__icon-button schedule__icon-button--danger"
                  onClick={() => void call("zamanlama.sil", { id: task.id }, "Görev silinemedi.")}
                  title="Sil"
                  type="button"
                >
                  <Icon name="trash" size={15} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      </div>

      {draft && (
        <div className="schedule__overlay" onMouseDown={(event) => { if (event.target === event.currentTarget) setDraft(null); }}>
          <div aria-label="Yeni zamanlanmış görev" aria-modal="true" className="schedule__dialog" role="dialog">
            <form aria-label="Yeni zamanlanmış görev" className="schedule__form" onSubmit={(event) => void submit(event)}>
              <h2>Yeni zamanlanmış görev</h2>
              {error && <p className="schedule__error" role="alert">{error}</p>}
              <label>Başlık<input onChange={(event) => update({ baslik: event.target.value })} placeholder="İsteğe bağlı" value={draft.baslik} /></label>
              <label>Görev<textarea onChange={(event) => update({ gorev: event.target.value })} placeholder="Fusion ne yapsın?" required rows={4} value={draft.gorev} /></label>
              <div className="schedule__row">
                <label>Ne zaman
                  <select onChange={(event) => update({ tur: event.target.value as ScheduleKind })} value={draft.tur}>
                    {(Object.keys(KIND_LABEL) as ScheduleKind[]).map((kind) => <option key={kind} value={kind}>{KIND_LABEL[kind]}</option>)}
                  </select>
                </label>
                {draft.tur === "bir_kez" && <label>Tarih<input onChange={(event) => update({ tarih: event.target.value })} required type="date" value={draft.tarih} /></label>}
                {draft.tur !== "aralik" && <label>Saat<input onChange={(event) => update({ saat: event.target.value })} required type="time" value={draft.saat} /></label>}
                {draft.tur === "aralik" && <label>Dakika<input min={15} onChange={(event) => update({ dakika: event.target.value })} required type="number" value={draft.dakika} /></label>}
              </div>
              {draft.tur === "haftalik" && (
                <div aria-label="Günler" className="schedule__days" role="group">
                  {DAY_LABELS.map((label, day) => (
                    <button aria-pressed={draft.gunler.includes(day)} key={label} onClick={() => toggleDay(day)} type="button">{label}</button>
                  ))}
                </div>
              )}
              <div className="schedule__folder">
                <span title={draft.kok}><Icon name="folder" size={14} /> {draft.kok || "Klasör seçilmedi"}</span>
                <button onClick={() => void chooseFolder(draft.kok).then((folder) => { if (folder) update({ kok: folder }); })} type="button">Değiştir</button>
              </div>
              <div className="schedule__form-actions">
                <button onClick={() => setDraft(null)} type="button">Vazgeç</button>
                <button className="schedule__primary" type="submit">Kaydet</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

/** Boş durum çizimi: marka çizgi diliyle kronometre. */
function StopwatchArt() {
  return (
    <svg aria-hidden="true" className="schedule__stopwatch" fill="none" height="84" viewBox="0 0 84 84" width="84">
      <rect height="7" rx="2" stroke="currentColor" strokeWidth="2.4" width="20" x="32" y="4" />
      <path d="M42 11v7" stroke="currentColor" strokeWidth="2.4" />
      <circle cx="42" cy="46" fill="currentColor" fillOpacity=".1" r="29" stroke="currentColor" strokeWidth="2.4" />
      <path d="M42 46V28M42 46l12 7" stroke="currentColor" strokeLinecap="round" strokeWidth="2.4" />
    </svg>
  );
}

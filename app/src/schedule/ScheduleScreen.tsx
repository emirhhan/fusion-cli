import { useCallback, useEffect, useState, type FormEvent } from "react";
import { selectDirectory } from "../platform/dialog";
import { Icon } from "../ui/Icon";
import { DAY_LABELS, describeSchedule, formatMoment, type ScheduleClient, type ScheduleKind, type ScheduledTask } from "./types";
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

  return (
    <div className="schedule">
      <header className="schedule__header" data-tauri-drag-region>
        <div>
          <h1>Zamanlananlar</h1>
          <p className="schedule__hint">Görevler Fusion açıkken çalışır; her çalışma yeni bir sohbet açar.</p>
        </div>
        <button className="schedule__primary" disabled={!client} onClick={() => { setError(null); setDraft(emptyDraft(defaultRoot)); }} type="button">
          <Icon name="new" size={16} /> Yeni görev
        </button>
      </header>
      {error && <p className="schedule__error" role="alert">{error}</p>}
      {draft && (
        <form aria-label="Yeni zamanlanmış görev" className="schedule__form" onSubmit={(event) => void submit(event)}>
          <label>Başlık<input onChange={(event) => update({ baslik: event.target.value })} placeholder="İsteğe bağlı" value={draft.baslik} /></label>
          <label>Görev<textarea onChange={(event) => update({ gorev: event.target.value })} placeholder="Fusion ne yapsın?" required rows={3} value={draft.gorev} /></label>
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
            <span title={draft.kok}>Klasör: {draft.kok || "seçilmedi"}</span>
            <button onClick={() => void chooseFolder(draft.kok).then((folder) => { if (folder) update({ kok: folder }); })} type="button">Değiştir</button>
          </div>
          <div className="schedule__form-actions">
            <button onClick={() => setDraft(null)} type="button">Vazgeç</button>
            <button className="schedule__primary" type="submit">Kaydet</button>
          </div>
        </form>
      )}
      {!client ? (
        <p className="schedule__empty">Zamanlananları görmek için Home'da bir sohbet aç.</p>
      ) : tasks.length === 0 && !draft ? (
        <p className="schedule__empty">Henüz zamanlanmış görev yok.</p>
      ) : (
        <ul aria-label="Zamanlanmış görevler" className="schedule__list">
          {tasks.map((task) => (
            <li className="schedule__item" data-enabled={task.etkin} key={task.id}>
              <div className="schedule__item-main">
                <p className="schedule__title">{task.baslik}</p>
                <p className="schedule__meta">
                  {describeSchedule(task)}
                  {task.etkin && task.sonraki ? ` · sıradaki ${formatMoment(task.sonraki)}` : task.sonraki ? " · duraklatıldı" : " · tamamlandı"}
                </p>
                {task.son_calisma && (
                  <p className="schedule__meta">Son çalışma {formatMoment(task.son_calisma)}{task.son_gecikmeli ? " (gecikmeli: Fusion kapalıydı)" : ""}</p>
                )}
              </div>
              <div className="schedule__actions">
                <button onClick={() => void runNow(task)} type="button">Şimdi çalıştır</button>
                {task.sonraki !== null && (
                  <button onClick={() => void call("zamanlama.etkin", { id: task.id, etkin: !task.etkin }, "Görev güncellenemedi.")} type="button">
                    {task.etkin ? "Duraklat" : "Sürdür"}
                  </button>
                )}
                <button aria-label={`${task.baslik} görevini sil`} onClick={() => void call("zamanlama.sil", { id: task.id }, "Görev silinemedi.")} type="button">Sil</button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

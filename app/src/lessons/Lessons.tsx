import { useCallback, useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import "./Lessons.css";

/**
 * Dersler ekranı — tasarım §12.
 *
 * Ders ayrı bir doküman okuyucusu DEĞİLDİR: her adım kullanıcının gerçek
 * çalışma alanında küçük ve geri alınabilir bir görevle ilerler. Bu ekran
 * hiçbir şey ÇALIŞTIRMAZ; yalnız var olan bir sekmeyi öne getirir ya da
 * composer'a hazır görev metnini koyar. Göndermeye ve onaylamaya kullanıcı
 * karar verir; mevcut onay/geri alma sözleşmesi değişmez.
 */

/** İlerleme kaydının anahtarı. Sürüm alanı ileride biçim değişirse gerekir. */
export const LESSON_PROGRESS_KEY = "fusion.lessons.progress.v1";

interface LessonSummary {
  id: string;
  baslik: string;
  ozet: string;
  adim_sayisi: number;
}

type LessonAction =
  | { tur: "composer"; gorev: string }
  | { tur: "sekme"; hedef: string };

interface LessonStep {
  id: string;
  baslik: string;
  aciklama: string;
  /** Kullanıcı denemeden ÖNCE ne olacağını gösteren metin. */
  onizleme: string;
  eylem: LessonAction;
}

interface LessonDetail {
  id: string;
  baslik: string;
  ozet: string;
  adimlar: LessonStep[];
}

/** Ders kimliği → tamamlanan adım sayısı. Başka HİÇBİR şey saklanmaz. */
export type LessonProgress = Record<string, number>;

/**
 * Kaydı oku. Bozuk, eski ya da erişilemez kayıt uygulamayı düşürmez;
 * sessizce boş ilerlemeye döner (özel pencere, temizlenmiş site verisi).
 */
export function readProgress(): LessonProgress {
  try {
    const raw = window.localStorage.getItem(LESSON_PROGRESS_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    const record = parsed as { surum?: unknown; ilerleme?: unknown };
    if (record.surum !== 1 || !record.ilerleme || typeof record.ilerleme !== "object") return {};
    const result: LessonProgress = {};
    for (const [id, step] of Object.entries(record.ilerleme as Record<string, unknown>)) {
      if (typeof step === "number" && Number.isInteger(step) && step >= 0) result[id] = step;
    }
    return result;
  } catch {
    return {};
  }
}

function writeProgress(progress: LessonProgress): void {
  try {
    window.localStorage.setItem(
      LESSON_PROGRESS_KEY,
      JSON.stringify({ surum: 1, ilerleme: progress }),
    );
  } catch {
    // Kayıt yazılamıyorsa ders yine çalışır; yalnız kaldığı yer hatırlanmaz.
  }
}

interface LessonsProps {
  client: ProtocolClient;
  onClose: () => void;
  onOpenTab: (hedef: string) => void;
  onUseComposer: (gorev: string) => void;
}

export function Lessons({ client, onClose, onOpenTab, onUseComposer }: LessonsProps) {
  const [lessons, setLessons] = useState<LessonSummary[]>([]);
  const [detail, setDetail] = useState<LessonDetail | null>(null);
  const [progress, setProgress] = useState<LessonProgress>(() => readProgress());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    void client
      .request("ders.listele", {})
      .then((veri) => {
        const payload = veri as { ok?: boolean; dersler?: LessonSummary[] };
        if (!live) return;
        if (!payload?.ok) {
          setError("Ders listesi alınamadı.");
          return;
        }
        setLessons(payload.dersler ?? []);
      })
      .catch(() => live && setError("Ders listesi alınamadı."));
    return () => {
      live = false;
    };
  }, [client]);

  const openLesson = useCallback(
    async (id: string) => {
      setError(null);
      try {
        const veri = (await client.request("ders.getir", { id })) as unknown as
          & { ok?: boolean; metin?: string }
          & LessonDetail;
        if (!veri?.ok) {
          setError(veri?.metin ?? "Ders açılamadı.");
          return;
        }
        setDetail({ id: veri.id, baslik: veri.baslik, ozet: veri.ozet, adimlar: veri.adimlar });
      } catch {
        setError("Ders açılamadı.");
      }
    },
    [client],
  );

  if (detail) {
    const done = progress[detail.id] ?? 0;
    const index = Math.min(done, detail.adimlar.length - 1);
    const step = detail.adimlar[index];
    const finished = done >= detail.adimlar.length;

    const complete = () => {
      const next = { ...progress, [detail.id]: Math.min(done + 1, detail.adimlar.length) };
      setProgress(next);
      writeProgress(next);
    };

    return (
      <section aria-label={`${detail.baslik} dersi`} className="lessons">
        <header className="lessons-header">
          <button className="lessons-back" onClick={() => setDetail(null)} type="button">
            ← Dersler
          </button>
          <h2>{detail.baslik}</h2>
          <p className="lessons-progress">
            {finished ? "Tamamlandı" : `${index + 1}. adım / ${detail.adimlar.length}`}
          </p>
        </header>
        <article className="lessons-step">
          <div aria-hidden="true" className="lessons-progress-bar">
            <span style={{ width: `${((index + 1) / detail.adimlar.length) * 100}%` }} />
          </div>
          <h3>{step.baslik}</h3>
          <p>{step.aciklama}</p>
          <div className="lessons-preview">
            <span className="lessons-preview__label">
              {step.eylem.tur === "composer" ? "Gönderilecek metin" : "Ne göreceksin"}
            </span>
            <p className="lessons-preview__body">{step.onizleme}</p>
          </div>
          <div className="lessons-actions">
            <button
              className="lessons-try"
              onClick={() =>
                step.eylem.tur === "composer"
                  ? onUseComposer(step.eylem.gorev)
                  : onOpenTab(step.eylem.hedef)
              }
              type="button"
            >
              Bunu dene
            </button>
            {!finished && (
              <button className="lessons-next" onClick={complete} type="button">
                Adımı tamamla
              </button>
            )}
          </div>
          <p className="lessons-note">
            {step.eylem.tur === "composer"
              ? "Metin yalnız görev kutusuna konur; sen göndermeden hiçbir şey çalışmaz."
              : "Yalnız ilgili sekme öne getirilir; hiçbir dosya değişmez."}
          </p>
        </article>
      </section>
    );
  }

  return (
    <section aria-label="Dersler" className="lessons">
      <header className="lessons-header">
        <h2>Dersler</h2>
        <button className="lessons-back" onClick={onClose} type="button">
          Sohbete dön
        </button>
      </header>
      {error && <p className="lessons-error">{error}</p>}
      <ul className="lessons-list">
        {lessons.map((lesson) => {
          const done = progress[lesson.id] ?? 0;
          return (
            <li key={lesson.id}>
              <button className="lessons-card" onClick={() => void openLesson(lesson.id)} type="button">
                <span className="lessons-card-title">{lesson.baslik}</span>
                <span className="lessons-card-summary">{lesson.ozet}</span>
                <span className="lessons-card-meta">
                  <span>{lesson.adim_sayisi} adım</span>
                  {done > 0 && (
                    <span className="lessons-card-done">
                      {done >= lesson.adim_sayisi ? "tamamlandı" : `${done} tamamlandı`}
                    </span>
                  )}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

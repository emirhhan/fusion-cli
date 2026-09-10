import "./EmptyState.css";
import { FusionAvatar, type AvatarState } from "../voice/FusionAvatar";

const suggestions = [
  "Yeni bir web projesi oluştur",
  "Bu projeyi incele ve eksikleri açıkla",
  "Claude veya Codex sohbetini sürdür",
];

/**
 * Boş sohbet ekranı.
 *
 * Burada Fusion'ın KENDİSİ durur: eskiden pixel bir "F" işareti vardı ve
 * ürünün karakteriyle ilgisi yoktu. İfade uygulamanın durumunu izler, böylece
 * karakter beklerken ve çalışırken aynı görünmez.
 */
export function EmptyState({
  durum = "idle",
  projectName,
  onSelectPrompt = () => undefined,
}: {
  durum?: AvatarState;
  projectName?: string;
  onSelectPrompt?: (prompt: string) => void;
}) {
  return (
    <section className="empty-state">
      <div className="empty-state__content">
        <div className="empty-state__character empty-state__character--uncropped">
          <FusionAvatar scale={1.35} state={durum} />
        </div>
        <h2>{projectName ? `${projectName} içinde ne üzerinde çalışıyoruz?` : "Bugün ne üzerinde çalışıyoruz?"}</h2>
        <p>Bir proje üret, mevcut kodu geliştir veya kaldığın konuşmayı sürdür.</p>
        <div aria-label="Başlangıç önerileri" className="empty-state__suggestions">
          {suggestions.map((suggestion) => (
            <button key={suggestion} onClick={() => onSelectPrompt(suggestion)} type="button">
              {suggestion}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

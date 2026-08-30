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
  onSelectPrompt = () => undefined,
}: {
  durum?: AvatarState;
  onSelectPrompt?: (prompt: string) => void;
}) {
  return (
    <section className="empty-state">
      <div className="empty-state__content">
        <div className="empty-state__character">
          <FusionAvatar scale={0.7} state={durum} />
        </div>
        <h2>Bugün ne üzerinde çalışıyoruz?</h2>
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

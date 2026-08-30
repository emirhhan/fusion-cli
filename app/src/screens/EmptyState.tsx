import "./EmptyState.css";
import { FusionPixel } from "../brand/FusionPixel";

const suggestions = [
  "Yeni bir web projesi oluştur",
  "Bu projeyi incele ve eksikleri açıkla",
  "Claude veya Codex sohbetini sürdür",
];

export function EmptyState({ onSelectPrompt = () => undefined }: {
  onSelectPrompt?: (prompt: string) => void;
}) {
  return (
    <section className="empty-state">
      <div className="empty-state__content">
        <div className="empty-state__character"><FusionPixel /></div>
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

import "./TierBar.css";

/** Composer'da gösterilen tek kademe. Çekirdekten olduğu gibi gelir. */
export interface Tier {
  ad: string;
  etiket: string;
  model: string;
}

interface TierBarProps {
  tiers: Tier[];
  active: string;
  /** Sağlayıcı NVIDIA'yı dışlıyorsa kademe seçilemez. */
  editable: boolean;
  /** Kilitliyken gösterilecek gerekçe. Kararı çekirdek verir, arayüz tahmin etmez. */
  reason?: string;
  onSelect: (ad: string) => void;
}

/**
 * Düşünme düzeyi çubuğu — gönder düğmesinin solunda durur.
 *
 * Neden burada: kademe hem gecikmeyi hem modeli değiştirir, yani kullanıcı bunu
 * GÖNDERMEDEN önce bilmek ister. Ayarlar ekranına gömülen bir seçim, her mesajda
 * yeniden düşünülmesi gereken bir kararı görünmez kılardı.
 *
 * Kilit sunucudan gelir: kademe modelleri NVIDIA'da barındığı için başka bir
 * sağlayıcı seçiliyken çubuk devre dışı kalır ve nedenini söyler.
 */
export function TierBar({ tiers, active, editable, reason, onSelect }: TierBarProps) {
  if (tiers.length === 0) return null;
  const index = Math.max(tiers.findIndex((tier) => tier.ad === active), 0);
  const current = tiers[index];

  return (
    <div
      aria-disabled={!editable}
      className="tier-bar"
      data-kilitli={!editable}
      title={editable ? current.etiket : reason}
    >
      <span className="tier-bar__label">{current.ad}</span>
      <div
        aria-label="Düşünme düzeyi"
        aria-orientation="horizontal"
        aria-valuemax={tiers.length}
        aria-valuemin={1}
        aria-valuenow={index + 1}
        aria-valuetext={`${current.ad} — ${current.etiket}`}
        className="tier-bar__track"
        onKeyDown={(event) => {
          if (!editable) return;
          const delta = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
          if (delta === 0) return;
          event.preventDefault();
          const next = Math.min(Math.max(index + delta, 0), tiers.length - 1);
          if (next !== index) onSelect(tiers[next].ad);
        }}
        role="slider"
        tabIndex={editable ? 0 : -1}
      >
        {tiers.map((tier, position) => (
          <button
            aria-label={`${tier.ad} — ${tier.etiket}`}
            className="tier-bar__step"
            data-secili={position === index}
            data-gecmis={position <= index}
            disabled={!editable}
            key={tier.ad}
            onClick={() => onSelect(tier.ad)}
            type="button"
          />
        ))}
      </div>
    </div>
  );
}

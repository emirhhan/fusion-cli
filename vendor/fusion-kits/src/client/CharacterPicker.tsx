import { characterImage, KIT_CHARACTERS } from '../shared/characters';

/** Kit karakteri seçici. Gerçek radyo düğmeleri: ok tuşlarıyla gezilir,
 * ekran okuyucu "Karakter, Mavi, 1/8" diye okur. */
export function CharacterPicker({
  value,
  used,
  onChange,
}: {
  value: string;
  /** Başka Kit'lerin kullandığı karakterler (seçilebilir, yalnız işaretlenir). */
  used: readonly string[];
  onChange: (character: string) => void;
}) {
  return (
    <fieldset className="character-picker">
      <legend>Karakter</legend>
      <div className="character-grid">
        {KIT_CHARACTERS.map((item) => (
          <label
            key={item.id}
            className={`character-option ${value === item.id ? 'selected' : ''}`}
            title={
              used.includes(item.id)
                ? `${item.label} (başka bir Kit kullanıyor)`
                : item.label
            }
          >
            <input
              type="radio"
              name="kit-character"
              value={item.id}
              checked={value === item.id}
              onChange={() => onChange(item.id)}
            />
            <img
              src={characterImage(item.id)}
              alt=""
              width={56}
              height={56}
              draggable={false}
            />
            <span>{item.label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

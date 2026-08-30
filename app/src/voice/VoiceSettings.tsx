import { useEffect, useRef, useState } from "react";

/**
 * Panel içi ses ayarları.
 *
 * Ayarlar için ana pencereye dönmek gerekmez: konuşurken duyduğun şeyi
 * konuşurken düzeltmek istersin. Değerler yalnız BIRAKINCA gönderilir;
 * sürgüyü sürüklerken her adımda çekirdeğe istek yollamak gereksiz.
 */

export interface VoicePrefs {
  /** 0,6–1,6 arası konuşma hızı çarpanı. */
  hiz: number;
  /** 0 doğal, 1 mekanik. */
  robotik: number;
  /** Seçilmiş Piper `.onnx` modeli; yoksa null. */
  model: string | null;
}

export function VoiceSettings({
  disabled = false,
  onChange,
  onPickModel,
  onTopChange,
  prefs,
  onTop,
  showOnTop = true,
}: {
  disabled?: boolean;
  onChange: (next: VoicePrefs) => void;
  onPickModel?: () => void;
  onTop: boolean;
  onTopChange: (next: boolean) => void;
  prefs: VoicePrefs;
  /** Ayrı ses penceresine özgü seçeneği ana Ayarlar kartında gösterme. */
  showOnTop?: boolean;
}) {
  const [taslak, setTaslak] = useState(prefs);
  const taslakRef = useRef(prefs);
  useEffect(() => {
    taslakRef.current = prefs;
    setTaslak(prefs);
  }, [prefs]);

  const guncelle = (next: VoicePrefs) => {
    // Windows WebView change + mouseUp olaylarını aynı React çevriminde
    // işleyebilir. State henüz çizilmeden mouseUp gelirse eski değer
    // kaydedilmesin diye son taslak eşzamanlı olarak ref'te de tutulur.
    taslakRef.current = next;
    setTaslak(next);
  };
  const kaydet = () => onChange(taslakRef.current);

  const dosyaAdi = taslak.model?.split(/[\\/]/).filter(Boolean).slice(-1)[0];

  return (
    <div className="voice-settings">
      <label className="voice-settings__row" htmlFor="ses-hiz">
        <span>Hız</span>
        <input
          disabled={disabled}
          id="ses-hiz"
          max={1.6}
          min={0.6}
          onChange={(event) => guncelle({ ...taslakRef.current, hiz: Number(event.target.value) })}
          onMouseUp={kaydet}
          onKeyUp={kaydet}
          onTouchEnd={kaydet}
          step={0.05}
          type="range"
          value={taslak.hiz}
        />
        <output>{taslak.hiz.toFixed(2)}×</output>
      </label>

      <label className="voice-settings__row" htmlFor="ses-robotik">
        <span>Robotik</span>
        <input
          disabled={disabled}
          id="ses-robotik"
          max={1}
          min={0}
          onChange={(event) =>
            guncelle({ ...taslakRef.current, robotik: Number(event.target.value) })
          }
          onMouseUp={kaydet}
          onKeyUp={kaydet}
          onTouchEnd={kaydet}
          step={0.05}
          type="range"
          value={taslak.robotik}
        />
        <output>{Math.round(taslak.robotik * 100)}%</output>
      </label>

      {showOnTop && (
        <label className="voice-settings__toggle">
          <input
            checked={onTop}
            disabled={disabled}
            onChange={(event) => onTopChange(event.target.checked)}
            type="checkbox"
          />
          <span>Hep üstte kal</span>
        </label>
      )}

      {onPickModel && (
        <div className="voice-settings__model">
          {/* Ad AÇIK: Fusion ses klonlamaz. Kullanıcının konuşma kaydı bir ses
              modeli değildir; "kendi ses dosyam" yazmak, WAV yükleyip ses
              klonlandığını sanmaya yol açıyordu. */}
          <button disabled={disabled} onClick={onPickModel} type="button">Piper ses modeli seç</button>
          <small>{dosyaAdi ?? "Fusion'ın Türkçe modeli kullanılıyor"}</small>
        </div>
      )}
    </div>
  );
}

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
}

export function VoiceSettings({
  disabled = false,
  onChange,
  onTopChange,
  prefs,
  onTop,
  showOnTop = true,
}: {
  disabled?: boolean;
  onChange: (next: VoicePrefs) => void;
  onTop: boolean;
  onTopChange: (next: boolean) => void;
  prefs: VoicePrefs;
  /** Ayrı ses penceresine özgü seçeneği ana Ayarlar kartında gösterme. */
  showOnTop?: boolean;
}) {
  const [taslak, setTaslak] = useState(prefs);
  const taslakRef = useRef(prefs);
  const sonPropsRef = useRef(prefs);
  useEffect(() => {
    // İlk mount'ta state zaten `prefs` ile kuruldu. Aynı değeri pasif effect'te
    // yeniden yazmak, hızlı bir ilk sürüklemenin hemen ardından çalışıp kullanıcı
    // taslağını eski değere döndürebiliyordu (özellikle yavaş CI/WebView'da).
    if (sonPropsRef.current === prefs) return;
    sonPropsRef.current = prefs;
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

    </div>
  );
}

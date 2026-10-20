// Diktasyon: tarayıcı SpeechRecognition (varsa). Ses sunucuya Fusion'dan geçmez; tarayıcının hizmetine gider.
export function voiceSupported() {
  return Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
}

export function createDictation({ onText, onState }) {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) return null;
  let recognition = null;
  return {
    toggle() {
      if (recognition) { recognition.stop(); return; }
      recognition = new Recognition();
      recognition.lang = "tr-TR";
      recognition.interimResults = true;
      recognition.continuous = false;
      recognition.onresult = (event) => {
        onText(Array.from(event.results).map((r) => r[0].transcript).join(" "), event.results[event.results.length - 1].isFinal);
      };
      recognition.onerror = (event) => onState("error", event.error);
      recognition.onend = () => { recognition = null; onState("idle"); };
      onState("listening");
      recognition.start();
    },
  };
}

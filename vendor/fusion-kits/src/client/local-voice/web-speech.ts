import type { ListenHandlers, VoiceEngine } from './engine';

/** Web Speech API'nin kullandığımız kadarı (tarayıcı tipleri her yerde yok). */
interface RecognitionResult {
  isFinal: boolean;
  0: { transcript: string };
}
interface RecognitionEvent {
  resultIndex: number;
  results: ArrayLike<RecognitionResult>;
}
export interface Recognition {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((event: RecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
export interface SpeechWindow {
  SpeechRecognition?: new () => Recognition;
  webkitSpeechRecognition?: new () => Recognition;
  speechSynthesis?: SpeechSynthesis;
  SpeechSynthesisUtterance?: typeof SpeechSynthesisUtterance;
}
const LANGUAGE = 'tr-TR';
const SPEECH_ERROR = 'Seslendirilemedi. Yanıt sohbette korunuyor.';
/** Türkçe seslerden en doğal duyulanlar (macOS ve Chrome adları). */
const PREFERRED_VOICES = ['Cem', 'Yelda', 'Google Türkçe'];
const ERROR_TEXT: Record<string, string> = {
  'not-allowed':
    'Mikrofon izni verilmedi. Tarayıcı ayarlarından mikrofona izin ver.',
  'service-not-allowed': 'Bu tarayıcı konuşma tanımaya izin vermiyor.',
  'audio-capture': 'Mikrofon bulunamadı.',
  network: 'Konuşma tanıma servisine ulaşılamadı.',
};

export function webSpeechSupported(view: SpeechWindow) {
  return !!(
    (view.SpeechRecognition ?? view.webkitSpeechRecognition) &&
    view.speechSynthesis &&
    view.SpeechSynthesisUtterance
  );
}

export function pickTurkishVoice(voices: readonly SpeechSynthesisVoice[]) {
  const turkish = voices.filter((voice) =>
    voice.lang.toLowerCase().startsWith('tr'),
  );
  for (const name of PREFERRED_VOICES) {
    const match = turkish.find((voice) => voice.name.includes(name));
    if (match) return match;
  }
  return turkish[0];
}

export class WebSpeechEngine implements VoiceEngine {
  readonly kind = 'browser' as const;
  private recognition?: Recognition;
  private listening = false;
  private finishSpeaking?: () => void;
  constructor(private view: SpeechWindow) {}

  async listen(handlers: ListenHandlers) {
    await this.stopListening();
    const Constructor =
      this.view.SpeechRecognition ?? this.view.webkitSpeechRecognition;
    if (!Constructor) throw new Error('Konuşma tanıma desteklenmiyor.');
    const recognition = new Constructor();
    recognition.lang = LANGUAGE;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.onresult = (event) => {
      for (
        let index = event.resultIndex;
        index < event.results.length;
        index++
      ) {
        const result = event.results[index];
        const text = result[0].transcript.trim();
        if (!text) continue;
        if (result.isFinal) handlers.onFinal(text);
        else handlers.onPartial(text);
      }
    };
    recognition.onerror = (event) => {
      if (event.error === 'no-speech' || event.error === 'aborted') return;
      this.listening = false;
      handlers.onError(ERROR_TEXT[event.error] ?? 'Konuşma tanınamadı.');
    };
    // Tarayıcı sessizlikte tanımayı kendiliğinden bitirir; dinleme sürüyorsa yeniden başlat.
    recognition.onend = () => {
      if (this.listening && this.recognition === recognition)
        try {
          recognition.start();
        } catch {
          this.listening = false;
        }
    };
    this.recognition = recognition;
    this.listening = true;
    recognition.start();
  }

  async stopListening() {
    this.listening = false;
    const current = this.recognition;
    this.recognition = undefined;
    if (!current) return;
    current.onend = null;
    current.onresult = null;
    try {
      current.abort();
    } catch {
      // Zaten durmuş.
    }
  }

  speak(text: string) {
    const synth = this.view.speechSynthesis;
    const Utterance = this.view.SpeechSynthesisUtterance;
    if (!synth || !Utterance) return Promise.reject(new Error(SPEECH_ERROR));
    return new Promise<void>((resolve, reject) => {
      const utterance = new Utterance(text);
      utterance.lang = LANGUAGE;
      const voice = pickTurkishVoice(synth.getVoices());
      if (voice) utterance.voice = voice;
      const done = (error?: Error) => {
        utterance.onend = null;
        utterance.onerror = null;
        if (this.finishSpeaking === done) this.finishSpeaking = undefined;
        if (error) reject(error);
        else resolve();
      };
      this.finishSpeaking = done;
      utterance.onend = () => done();
      utterance.onerror = () => done(new Error(SPEECH_ERROR));
      try {
        synth.speak(utterance);
      } catch {
        done(new Error(SPEECH_ERROR));
      }
    });
  }

  async stopSpeaking() {
    this.finishSpeaking?.();
    this.view.speechSynthesis?.cancel();
  }

  close() {
    void this.stopListening();
    void this.stopSpeaking();
  }
}

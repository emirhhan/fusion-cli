import { api } from '../api';
import { NO_VOICE_MESSAGE, type VoiceEngine } from './engine';
import { FusionVoiceEngine } from './fusion-bridge';
import {
  WebSpeechEngine,
  webSpeechSupported,
  type SpeechWindow,
} from './web-speech';

/** Önce Fusion'ın yerel sesi (en iyi Türkçe, çevrimdışı), yoksa tarayıcının sesi. */
export async function detectVoiceEngine(): Promise<VoiceEngine> {
  const fusion = await FusionVoiceEngine.connect(window, api);
  if (fusion) return fusion;
  const view = window as unknown as SpeechWindow;
  if (webSpeechSupported(view)) return new WebSpeechEngine(view);
  throw new Error(NO_VOICE_MESSAGE);
}

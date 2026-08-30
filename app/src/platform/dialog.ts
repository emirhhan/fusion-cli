import { open } from "@tauri-apps/plugin-dialog";

/** İşletim sisteminin yerel klasör seçicisini açar. */
export async function selectDirectory(defaultPath?: string): Promise<string | null> {
  const selected = await open({
    defaultPath: defaultPath || undefined,
    directory: true,
    multiple: false,
    title: "Fusion çalışma klasörünü seç",
  });
  return typeof selected === "string" ? selected : null;
}

/** Ataç düğmesi için bir veya daha fazla yerel dosya seçer. */
export async function selectFiles(defaultPath?: string): Promise<string[]> {
  const selected = await open({
    defaultPath: defaultPath || undefined,
    directory: false,
    multiple: true,
    title: "Fusion'a dosya ekle",
  });
  if (Array.isArray(selected)) return selected;
  return typeof selected === "string" ? [selected] : [];
}

/**
 * Piper ses modeli seçer.
 *
 * Süzgeç `.onnx` ile SINIRLI: Fusion ses klonlamaz ve kullanıcının konuşma
 * kaydı (WAV/MP3) bir ses modeli değildir. Süzgeç olmadan kullanıcı ses
 * kaydını seçip klonlandığını sanıyor, hata çok sonra Piper'dan geliyordu.
 */
export async function selectVoiceModel(): Promise<string | null> {
  const selected = await open({
    directory: false,
    filters: [{ extensions: ["onnx"], name: "Piper ses modeli" }],
    multiple: false,
    title: "Piper ses modeli seç (.onnx)",
  });
  return typeof selected === "string" ? selected : null;
}

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

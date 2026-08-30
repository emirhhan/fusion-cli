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

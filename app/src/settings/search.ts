export type SettingsSection = "genel" | "hesap" | "ses" | "kisisellestirme" | "modeller" | "tarayici" | "izinler" | "uzak" | "guncellemeler" | "gelismis";
interface SettingsRow { section: SettingsSection; id: string; label: string; keywords: string }
export const SETTINGS_ROWS: SettingsRow[] = [
  { section: "genel", id: "settings-theme", label: "Tema", keywords: "görünüm koyu açık sistem" },
  { section: "genel", id: "settings-history", label: "Geçmiş", keywords: "sohbet kenar çubuğu" },
  { section: "gelismis", id: "settings-gateway", label: "Yerel API ucu", keywords: "gateway cursor cline bağlantı" },
  { section: "uzak", id: "settings-remote", label: "Uzaktan Erişim", keywords: "telefon pwa telegram eşleştir cihaz uzak" },
  { section: "kisisellestirme", id: "settings-memory", label: "Bellek", keywords: "hafıza anı kişiselleştirme" },
];
export function searchSettings(query: string): SettingsRow[] {
  const text = query.trim().toLocaleLowerCase("tr");
  return text ? SETTINGS_ROWS.filter((row) => `${row.label} ${row.keywords}`.toLocaleLowerCase("tr").includes(text)) : [];
}

export type SettingsSection = "genel" | "hesap" | "ses" | "kisisellestirme" | "modeller" | "tarayici" | "izinler" | "zeka" | "uzak" | "guncellemeler" | "gelismis" | "nasil";
interface SettingsRow { section: SettingsSection; id: string; label: string; keywords: string }
export const SETTINGS_ROWS: SettingsRow[] = [
  { section: "genel", id: "settings-theme", label: "Tema", keywords: "görünüm koyu açık sistem" },
  { section: "genel", id: "settings-history", label: "Geçmiş", keywords: "sohbet kenar çubuğu" },
  { section: "gelismis", id: "settings-gateway", label: "Yerel API ucu", keywords: "gateway cursor cline bağlantı" },
  { section: "zeka", id: "settings-intelligence", label: "Zeka", keywords: "motor fusion plan öz-denetim ders öğretmen doğrulama playbook yansıma kendini geliştir" },
  { section: "uzak", id: "settings-remote", label: "Uzaktan Erişim", keywords: "telefon pwa telegram eşleştir cihaz uzak" },
  { section: "nasil", id: "settings-howto", label: "Nasıl yapılır", keywords: "eğitim rehber yardım ekran görüntüsü adım adım tailscale chrome kits ses" },
  { section: "kisisellestirme", id: "settings-memory", label: "Bellek", keywords: "hafıza anı kişiselleştirme" },
];
export function searchSettings(query: string): SettingsRow[] {
  const text = query.trim().toLocaleLowerCase("tr");
  return text ? SETTINGS_ROWS.filter((row) => `${row.label} ${row.keywords}`.toLocaleLowerCase("tr").includes(text)) : [];
}

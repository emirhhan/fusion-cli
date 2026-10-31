export type SettingsSection = "genel" | "hesap" | "bildirimler" | "ses" | "kisisellestirme" | "modeller" | "tarayici" | "weboturumlari" | "izinler" | "zeka" | "uzak" | "guncellemeler" | "gelismis" | "nasil";
interface SettingsRow { section: SettingsSection; id: string; label: string; keywords: string }
/** Bölüm başlığının kimliği; satır kimliği olmayan bölümler buna odaklanır. */
export const SECTION_HEADING_ID = "settings-section-heading";
export const SETTINGS_ROWS: SettingsRow[] = [
  { section: "genel", id: "settings-theme", label: "Tema", keywords: "görünüm koyu açık sistem" },
  { section: "genel", id: "settings-history", label: "Geçmiş", keywords: "sohbet kenar çubuğu" },
  { section: "genel", id: "settings-tray", label: "Menü çubuğu simgesi", keywords: "tepsi tray sistem simge menü çubuğu" },
  { section: "genel", id: "settings-language", label: "Dil", keywords: "language english ingilizce türkçe" },
  { section: "genel", id: "settings-font-scale", label: "Erişilebilirlik", keywords: "yazı boyutu ölçek büyük küçük kontrast hareket animasyon azalt vurgu rengi accessibility" },
  { section: "bildirimler", id: "settings-notifications", label: "Bildirimler", keywords: "bildirim rozet okunmamış ses uyarı tur bitti onay dock" },
  { section: "gelismis", id: "settings-gateway", label: "Yerel API ucu", keywords: "gateway cursor cline bağlantı" },
  { section: "zeka", id: "settings-intelligence", label: "Zeka", keywords: "motor fusion plan öz-denetim ders öğretmen doğrulama playbook yansıma kendini geliştir" },
  { section: "uzak", id: "settings-remote", label: "Uzaktan Erişim", keywords: "telefon pwa telegram eşleştir cihaz uzak" },
  { section: "nasil", id: "settings-howto", label: "Nasıl yapılır", keywords: "eğitim rehber yardım ekran görüntüsü adım adım tailscale chrome kits ses" },
  { section: "kisisellestirme", id: "settings-memory", label: "Bellek", keywords: "hafıza anı kişiselleştirme" },
  // Kendi satır kimliği olmayan bölümler: bölüm başlığına odaklanır (Settings.tsx `settings-section-heading`).
  { section: "ses", id: SECTION_HEADING_ID, label: "Ses ve konuşma ayarları", keywords: "konuşma hız mikrofon talk seslendirme" },
  { section: "modeller", id: SECTION_HEADING_ID, label: "Model seçimi", keywords: "model sağlayıcı rol varsayılan görsel sohbet profil" },
  { section: "izinler", id: SECTION_HEADING_ID, label: "İzin modu", keywords: "onay mod çalışma klasörü kök manuel otomatik güven trust klasör dışı engel" },
  { section: "izinler", id: "settings-permission-rules", label: "İzin kuralları", keywords: "allow ask deny kural kalıp bash edit read webfetch mcp yasak her zaman sor bir daha sorma" },
  { section: "tarayici", id: SECTION_HEADING_ID, label: "Tarayıcı eklentisi", keywords: "chrome eklenti eşleştirme anahtar" },
  { section: "weboturumlari", id: SECTION_HEADING_ID, label: "Web oturumları", keywords: "çerez cookie oturum profil içe aktar chrome giriş tarayıcı" },
  { section: "kisisellestirme", id: SECTION_HEADING_ID, label: "Özel talimat", keywords: "özel talimat sistem istemi kişiselleştirme" },
  { section: "gelismis", id: SECTION_HEADING_ID, label: "Kullanım sayacı", keywords: "sayaç token maliyet kullanım istatistik" },
  { section: "gelismis", id: SECTION_HEADING_ID, label: "Hız sınırları ve kota", keywords: "kota limit hız sınırı 429 bekletiyor dakika istek" },
  { section: "guncellemeler", id: SECTION_HEADING_ID, label: "Sürüm güncellemesi", keywords: "sürüm yeni sürüm yükle güncelle" },
  { section: "guncellemeler", id: "settings-release-notes", label: "Sürüm notları", keywords: "sürüm notları neler değişti kanal kararlı changelog release notes" },
  { section: "kisisellestirme", id: "settings-import", label: "Başka araçtan içe aktar", keywords: "import içe aktar taşı claude code codex gemini cursor mcp izin komut kural" },
  { section: "uzak", id: "settings-remote", label: "Uzaktan kontrol", keywords: "remote control telefondan sür başlık anahtar /rc" },
];
export function searchSettings(query: string): SettingsRow[] {
  const text = query.trim().toLocaleLowerCase("tr");
  return text ? SETTINGS_ROWS.filter((row) => `${row.label} ${row.keywords}`.toLocaleLowerCase("tr").includes(text)) : [];
}

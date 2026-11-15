import { SETTINGS_ROWS, type SettingsSection } from "../settings/search";
import { actionLabel, formatKey, keysForAction, type Keymap } from "./keys";
import type { PaletteItem } from "./paletteItems";

/**
 * Paletin kaynakları (P-046): eylemler (kısayol tablosundaki her eylem, tuşuyla), ekranlar,
 * sohbetler, slash komutları ve ayar satırları. Dosyalar sorguya göre çekirdekten gelir
 * (`CommandPalette.searchFiles`). Öğeyi çalıştırmak uygulama kabuğunun işidir; burada
 * yalnız liste kurulur.
 */

/** Ekran hedefi: `main:<bölüm>` ana menü, diğerleri kenar çubuğu hedefi (`navigateSidebar`). */
export const PALETTE_SCREENS: { id: string; label: string; keywords: string }[] = [
  { id: "main:home", label: "Ana sayfa", keywords: "sohbet giriş home" },
  { id: "main:scheduled", label: "Zamanlananlar", keywords: "zamanlanmış görev cron döngü takvim" },
  { id: "main:library", label: "Kitaplık", keywords: "galeri dosya yüklenen görsel" },
  { id: "main:kits", label: "Kits", keywords: "kit uygulama" },
  { id: "image-create", label: "Görsel oluştur", keywords: "resim görsel üret medya" },
  { id: "skills", label: "Beceriler ve Ajanlar", keywords: "beceri skill ajan agent" },
  { id: "connectors", label: "Bağlantılar", keywords: "mcp bağlayıcı connector entegrasyon" },
  { id: "control-panel", label: "Kontrol Paneli", keywords: "sağlayıcı anahtar provider" },
  { id: "account", label: "Hesabım", keywords: "hesap profil avatar" },
  { id: "help", label: "Yardım", keywords: "sss nasıl kısayol" },
  { id: "feedback", label: "Geri bildirim gönder", keywords: "hata bildir rapor" },
];

export interface PaletteChat {
  id: string;
  title: string;
  project: string;
}

export interface PaletteCommand {
  ad: string;
  aciklama?: string;
}

export interface PaletteSourceInput {
  keymap: Keymap;
  mac: boolean;
  chats: readonly PaletteChat[];
  commands: readonly PaletteCommand[];
  runAction: (action: string) => void;
  openScreen: (id: string) => void;
  openChat: (id: string) => void;
  insertCommand: ((name: string) => void) | null;
  openSettings: (section: SettingsSection) => void;
}

const isPaletteAction = (action: string) => action !== "palet" && !/^sohbet_[1-9]$/.test(action);

export function buildPaletteItems(input: PaletteSourceInput): PaletteItem[] {
  const { keymap, mac } = input;
  const actions: PaletteItem[] = Object.keys(keymap.etiketler).filter(isPaletteAction).map((action) => ({
    id: `eylem:${action}`,
    kind: "eylem",
    label: actionLabel(action, keymap.etiketler),
    shortcut: keysForAction(keymap.baglar, action).map((key) => formatKey(key, mac))[0],
    run: () => input.runAction(action),
  }));
  const screens: PaletteItem[] = PALETTE_SCREENS.map((screen) => ({
    id: `ekran:${screen.id}`, kind: "ekran", label: screen.label, keywords: screen.keywords, run: () => input.openScreen(screen.id),
  }));
  const chats: PaletteItem[] = input.chats.map((chat) => ({
    id: `sohbet:${chat.id}`, kind: "sohbet", label: chat.title || "Adsız sohbet", detail: chat.project, run: () => input.openChat(chat.id),
  }));
  const insert = input.insertCommand;
  const commands: PaletteItem[] = insert
    ? input.commands.map((command) => ({
      id: `komut:${command.ad}`, kind: "komut", label: `/${command.ad}`, detail: command.aciklama, run: () => insert(command.ad),
    }))
    : [];
  const settings: PaletteItem[] = SETTINGS_ROWS.map((row) => ({
    id: `ayar:${row.section}:${row.label}`, kind: "ayar", label: row.label, keywords: row.keywords, detail: "Ayarlar", run: () => input.openSettings(row.section),
  }));
  return [...actions, ...screens, ...chats, ...commands, ...settings];
}

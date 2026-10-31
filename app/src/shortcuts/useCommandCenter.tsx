import { useCallback, useRef, useState, type ReactNode } from "react";
import type { SettingsSection } from "../settings/search";
import { runAppAction, type AppActionDeps } from "./appActions";
import { CommandPalette } from "./CommandPalette";
import { isMacPlatform } from "./keys";
import type { PaletteItem } from "./paletteItems";
import { buildPaletteItems, type PaletteChat, type PaletteCommand } from "./paletteSources";
import { useGlobalShortcuts, useKeymap } from "./useAppShortcuts";

/**
 * Uygulama kabuğunun kısayol + palet merkezi (P-046).
 *
 * `SessionApplication` her çizimde güncel işlevleri verir; dinleyici bir kez kurulur ve işlevleri
 * ref'ten okur (eski kapanış yakalanmaz). Dönen düğüm açık paletin kendisidir; kabuk onu her
 * ekranda (boş uygulama dahil) çizer.
 */

interface RequestClient {
  request(name: string, data: Record<string, unknown>): Promise<unknown>;
}

export interface CommandCenterInput {
  client: RequestClient | null;
  /** Hesap kapısı / kurulum sihirbazı açıkken kısayollar çalışmaz. */
  blocked: boolean;
  actions: Omit<AppActionDeps, "openPalette">;
  chats: readonly PaletteChat[];
  commands: readonly PaletteCommand[];
  openScreen: (id: string) => void;
  openChat: (id: string) => void;
  openFile: ((path: string) => void) | null;
  insertCommand: ((name: string) => void) | null;
  openSettings: (section: SettingsSection) => void;
}

const FILE_LIMIT = 20;

export function useCommandCenter(input: CommandCenterInput): ReactNode {
  const keymap = useKeymap(input.client);
  const [query, setQuery] = useState<string | null>(null);
  const inputRef = useRef(input);
  inputRef.current = input;
  const deps = (): AppActionDeps => ({
    ...inputRef.current.actions,
    openPalette: (next) => setQuery((current) => (current === next ? null : next)),
  });
  const handler = useRef<(action: string) => boolean>(() => false);
  handler.current = (action) => {
    if (inputRef.current.blocked) return false;
    if (query !== null && action !== "palet" && action !== "dosya_ara") setQuery(null);
    return runAppAction(action, deps());
  };
  useGlobalShortcuts(keymap.baglar, handler);

  // Kararlı kimlik: palet açıkken kabuk sık çizilir (akış); arama efekti her çizimde yeniden kurulmasın.
  const searchFiles = useCallback(async (text: string): Promise<PaletteItem[]> => {
    const { client, openFile } = inputRef.current;
    if (!client || !openFile) return [];
    const payload = (await client.request("proje.dosya_ara", { sorgu: text, limit: FILE_LIMIT })) as { sonuclar?: unknown };
    const rows = Array.isArray(payload?.sonuclar) ? payload.sonuclar : [];
    return rows
      .map((row) => (row as { yol?: unknown }).yol)
      .filter((path): path is string => typeof path === "string")
      .map((path) => ({ id: `dosya:${path}`, kind: "dosya" as const, label: path.split("/").pop() || path, detail: path, run: () => inputRef.current.openFile?.(path) }));
  }, []);

  if (query === null) return null;
  const items = buildPaletteItems({
    keymap,
    mac: isMacPlatform(),
    chats: input.chats,
    commands: input.commands,
    runAction: (action) => { runAppAction(action, deps()); },
    openScreen: input.openScreen,
    openChat: input.openChat,
    insertCommand: input.insertCommand,
    openSettings: input.openSettings,
  });
  return (
    <CommandPalette
      initialQuery={query}
      items={items}
      key={query}
      onClose={() => setQuery(null)}
      searchFiles={input.client && input.openFile ? searchFiles : undefined}
    />
  );
}

import { cycleViewMode } from "../settings/viewMode";
import { COMMAND_PREFIX } from "./keys";

/**
 * Uygulama eylemleri (P-046): kısayol tablosu ve komut paleti AYNI eylem adlarını çalıştırır.
 * Eylemin nasıl yapılacağını uygulama kabuğu verir (`AppActionDeps`); burada yalnız ad → iş
 * eşlemesi durur, böylece yeni eylem tek satırla eklenir ve iki yüzey ayrışmaz.
 */
export interface AppActionDeps {
  openPalette: (query: string) => void;
  newChat: () => void;
  openSettings: (section?: "kisayollar") => void;
  toggleSidebar: () => void;
  toggleTerminal: () => void;
  openPreview: () => void;
  toggleInspector: () => void;
  back: () => void;
  forward: () => void;
  /** Açık sohbetlerden sıradakine geç (0 tabanlı); yoksa `false`. */
  selectChat: (index: number) => boolean;
  openHistory: () => void;
  share: () => void;
  help: () => void;
  closeSplit: () => void;
  /** Açık oturumlar arasında ileri (+1) ya da geri (-1); tek oturumda `false` (#444). */
  cycleChat: (step: 1 | -1) => boolean;
  /** Etkin oturumu kapat (Claude Desktop ⌘W); oturum yoksa `false`. */
  closeActiveSession: () => boolean;
  toggleDiff: () => void;
  closePane: () => void;
  /** Yan sohbeti aç/kapat (Claude Desktop ⌘;, #444); etkin oturum yoksa verilmez. */
  toggleSideChat?: () => void;
  /** `komut:<ad>` bağı: slash komutunu çalıştır. */
  runCommand: (command: string) => void;
}

/** ⌘P paletin dosya kipinde açılışı: sorgu bu önekle başlar. */
export const FILE_QUERY_PREFIX = "@";

/** Eylemi çalıştır; tanınmayan ya da şu an uygulanamayan eylemde `false`. */
export function runAppAction(action: string, deps: AppActionDeps): boolean {
  if (action.startsWith(COMMAND_PREFIX)) {
    const name = action.slice(COMMAND_PREFIX.length).trim();
    if (!name) return false;
    deps.runCommand(`/${name}`);
    return true;
  }
  const chat = /^sohbet_([1-9])$/.exec(action);
  if (chat) return deps.selectChat(Number(chat[1]) - 1);
  const simple: Record<string, () => void> = {
    palet: () => deps.openPalette(""),
    dosya_ara: () => deps.openPalette(FILE_QUERY_PREFIX),
    yeni_sohbet: deps.newChat,
    ayarlar: () => deps.openSettings(),
    kisayollar: () => deps.openSettings("kisayollar"),
    kenar_cubugu: deps.toggleSidebar,
    terminal: deps.toggleTerminal,
    onizleme: deps.openPreview,
    denetci: deps.toggleInspector,
    geri: deps.back,
    ileri: deps.forward,
    gecmis: deps.openHistory,
    paylas: deps.share,
    yardim: deps.help,
    bolmeyi_kapat: deps.closeSplit,
    fark_paneli: deps.toggleDiff,
    paneli_kapat: deps.closePane,
    // Claude Desktop Ctrl+O: Verbose / Normal / Summary (#444).
    gorunum_kipi: () => { cycleViewMode(); },
  };
  if (action === "sonraki_oturum") return deps.cycleChat(1);
  if (action === "onceki_oturum") return deps.cycleChat(-1);
  if (action === "oturumu_kapat") return deps.closeActiveSession();
  if (action === "yan_sohbet") {
    if (!deps.toggleSideChat) return false;
    deps.toggleSideChat();
    return true;
  }
  const run = simple[action];
  if (!run) return false;
  run();
  return true;
}

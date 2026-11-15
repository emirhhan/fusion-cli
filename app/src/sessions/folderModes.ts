import type { ApprovalMode } from "../screens/ApprovalModeMenu";
import { bypassAllowed } from "./bypassGate";

/**
 * Seçilen izin modu klasör başına hatırlanır (#451).
 *
 * Claude Code Desktop: "A mode you pick in the selector is remembered per folder and takes
 * precedence over `defaultMode` for that folder, except Plan, which applies to the current
 * session only." Kayıt bu bilgisayarın tarayıcı deposundadır; okunamazsa (gizli pencere, kapalı
 * depo) hatırlama yapılmaz, uygulama yine çalışır.
 *
 * Hatırlanan "İzinleri atla" yalnız Ayarlar'daki anahtar (#442) açıkken geçerlidir: anahtar
 * kapatılınca o klasör hatırlanan modla değil `defaultMode` ile açılır. Ölçüldü (1 Kasım,
 * bağımsız inceleme): anahtar kapalıyken hatırlanan bypass oturuma sessizce uygulanıyordu.
 */
const KEY = "fusion.folderApprovalModes";
const MODES: readonly ApprovalMode[] = ["security", "edits", "plan", "auto", "bypass"];

function readAll(): Record<string, ApprovalMode> {
  try {
    const raw = JSON.parse(window.localStorage.getItem(KEY) ?? "{}") as unknown;
    if (!raw || typeof raw !== "object") return {};
    return Object.fromEntries(
      Object.entries(raw as Record<string, unknown>).filter(
        (entry): entry is [string, ApprovalMode] => MODES.includes(entry[1] as ApprovalMode),
      ),
    );
  } catch {
    return {};
  }
}

export function folderMode(root: string | undefined): ApprovalMode | undefined {
  if (!root) return undefined;
  const mode = readAll()[root];
  return mode === "bypass" && !bypassAllowed() ? undefined : mode;
}

export function rememberFolderMode(root: string | undefined, mode: ApprovalMode): void {
  if (!root || mode === "plan") return; // Plan yalnız bu oturum içindir.
  if (mode === "bypass" && !bypassAllowed()) return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify({ ...readAll(), [root]: mode }));
  } catch {
    // Depo kapalı: hatırlama yok, seçim bu oturumda geçerli.
  }
}

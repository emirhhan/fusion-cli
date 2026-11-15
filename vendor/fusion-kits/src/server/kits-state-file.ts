import {
  chmodSync,
  mkdirSync,
  readFileSync,
  renameSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs';
import { dirname, join } from 'node:path';

/**
 * Kits'in dinlediği adresi Fusion çekirdeğine (Python CLI/masaüstü oturumu) duyuran
 * durum dosyası. Masaüstü `KITS_STATE_FILE` ile yolu verir; Fusion aynı yolu
 * `config/paths.py kits_state_file()` ile türetir. Dosya adres ve pid dışında hiçbir
 * sır taşımaz (Kits yerel bağlantıda owner token kullanmaz). Chrome köprüsünün
 * `chrome-bridge.json` deseniyle aynıdır: atomik yazım, 0600, yalnız kendi pid'ini siler.
 */
export interface KitsState {
  fusion_kits_bridge: 1;
  url: string;
  pid: number;
  startedAt: number;
}

export function kitsStateFile(
  env: Record<string, string | undefined>,
): string | undefined {
  const path = env.KITS_STATE_FILE?.trim();
  return path || undefined;
}

export function writeKitsState(path: string, url: string, pid: number): void {
  const parsed = new URL(url);
  if (
    parsed.protocol !== 'http:' ||
    !['127.0.0.1', 'localhost', '[::1]'].includes(parsed.hostname)
  )
    throw new Error('Kits durum dosyası yalnız yerel HTTP adresi taşır.');
  const state: KitsState = {
    fusion_kits_bridge: 1,
    url: `${parsed.protocol}//${parsed.host}`,
    pid,
    startedAt: Date.now(),
  };
  mkdirSync(dirname(path), { recursive: true });
  const temporary = join(
    dirname(path),
    `.kits-bridge.${pid}.${Date.now().toString(36)}.tmp`,
  );
  writeFileSync(temporary, JSON.stringify(state), { mode: 0o600 });
  try {
    chmodSync(temporary, 0o600);
    renameSync(temporary, path);
  } catch (error) {
    try {
      unlinkSync(temporary);
    } catch {
      // Geçici dosya zaten yok.
    }
    throw error;
  }
}

/** Yalnız bu sürecin yazdığı durumu sil; yeni başlayan başka Kits'in kaydını ezme. */
export function clearKitsState(path: string, pid: number): void {
  try {
    const current = JSON.parse(
      readFileSync(path, 'utf8'),
    ) as Partial<KitsState>;
    if (current.pid === pid) unlinkSync(path);
  } catch {
    // Dosya yok ya da okunamıyor: silinecek bir şey yok.
  }
}

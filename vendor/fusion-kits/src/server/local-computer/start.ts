import { randomBytes } from 'node:crypto';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import type { PlatformConfig } from '../platform-config.js';
import { LocalSupervisor } from './supervisor.js';

export interface LocalComputerHandle {
  /** PlatformConfig'e eklenecek alanlar (yalnız bellekte; .env'e yazılmaz). */
  config: Pick<
    PlatformConfig,
    | 'computerSupervisorUrl'
    | 'computerSupervisorToken'
    | 'computerToken'
    | 'computerLocal'
  >;
  close(): Promise<void>;
}

/** Kits veri dizinindeki computers/ klasörü; bellek içi veritabanında geçici dizin. */
export function computersRoot(database: string) {
  return database === ':memory:'
    ? mkdtempSync(join(tmpdir(), 'fusion-kits-computers-'))
    : join(dirname(resolve(database)), 'computers');
}

/**
 * COMPUTER_SUPERVISOR_URL boşsa ve KITS_LOCAL_COMPUTER=0 değilse yerel denetçiyi
 * 127.0.0.1'de başlatır. Belirteçler rastgeledir ve yalnız bellekte tutulur.
 */
export async function startLocalComputer(
  env: NodeJS.ProcessEnv,
  database: string,
): Promise<LocalComputerHandle | undefined> {
  if (env.KITS_LOCAL_COMPUTER === '0' || env.COMPUTER_SUPERVISOR_URL?.trim())
    return;
  const supervisorToken = randomBytes(32).toString('hex');
  const computerToken = randomBytes(32).toString('hex');
  const supervisor = new LocalSupervisor({
    rootDir: computersRoot(database),
    supervisorToken,
    computerToken,
    namespace: env.COMPUTER_NAMESPACE || undefined,
  });
  let url: string;
  try {
    url = await supervisor.start();
  } catch (error) {
    console.warn(
      `Yerel Kit bilgisayarı başlatılamadı, bilgisayar özelliği kapalı: ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
    return;
  }
  console.log(`Kit bilgisayarı (yerel, Docker'sız): ${url}`);
  return {
    config: {
      computerSupervisorUrl: url,
      computerSupervisorToken: supervisorToken,
      computerToken,
      computerLocal: true,
    },
    close: () => supervisor.close(),
  };
}

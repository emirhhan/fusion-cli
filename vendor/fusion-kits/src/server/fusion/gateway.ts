/**
 * Kits model çağrılarını Fusion'ın yerel geçidinden (`fusion serve`) geçirir.
 *
 * Kits eskiden sağlayıcıya doğrudan, tek yeniden denemeyle bağlanıyordu (NVIDIA, maxRetries 1).
 * Fusion'ın ucuz model korumaları — 429 sonrası bekleme, sağlayıcı/model yedeği, hesap
 * havuzu, sağlık takibi, araç çağrısı emülasyonu — Kits'in kendi döngüsünde yoktu. Geçit
 * bunların hepsini aynı OpenAI uyumlu `/v1` adresinde sunar; yalnız 127.0.0.1'de dinler.
 */
import { spawn as nodeSpawn } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { createServer } from 'node:net';
import { join } from 'node:path';
import type { FusionConfig } from './config.js';
import { fusionEnv } from './transport.js';

export interface FusionGateway {
  baseUrl: string;
  close(): Promise<void>;
}

interface GatewayDeps {
  spawn?: typeof nodeSpawn;
  fetch?: typeof fetch;
  port?: () => Promise<number>;
  timeoutMs?: number;
  pollMs?: number;
}

/** `... app` ile biten Fusion argv'sinden aynı çekirdeğin `serve` komutunu türet. */
export function gatewayArgs(
  config: FusionConfig,
  port: number,
): string[] | undefined {
  if (config.args.at(-1) !== 'app') return;
  return [
    ...config.args.slice(0, -1),
    'serve',
    '--host',
    '127.0.0.1',
    '--port',
    String(port),
    // Kits uzun sohbetin tamamını her turda gönderir; geçit bütçeyi aşan geçmişi özetler.
    '--compact-context',
  ];
}

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      server.close(() =>
        typeof address === 'object' && address
          ? resolve(address.port)
          : reject(new Error('Boş port bulunamadı.')),
      );
    });
  });
}

/** Yalnız model geçidi açık kullanıcı paylaşımında kayıtlı sağlayıcı kasasını kullanır. */
export function gatewayEnvironment(
  config: FusionConfig,
  home: string,
): Record<string, string> {
  const env = fusionEnv(config, home);
  if (config.userConfigHome) {
    env.XDG_DATA_HOME = join(config.userConfigHome, '.local', 'share');
    env.LOCALAPPDATA = join(config.userConfigHome, 'AppData', 'Local');
  }
  return env;
}

export async function startFusionGateway(
  config: FusionConfig,
  deps: GatewayDeps = {},
): Promise<FusionGateway> {
  const spawn = deps.spawn ?? nodeSpawn;
  const request = deps.fetch ?? fetch;
  const timeoutMs = deps.timeoutMs ?? 45_000;
  const pollMs = deps.pollMs ?? 250;
  const port = await (deps.port ?? freePort)();
  const args = gatewayArgs(config, port);
  if (!args)
    throw new Error(
      "Fusion geçidi başlatılamadı: FUSION_ARGS 'app' ile bitmiyor.",
    );
  const home = join(config.home, 'gateway');
  mkdirSync(home, { recursive: true });
  const child = spawn(config.command, args, {
    cwd: config.root,
    env: gatewayEnvironment(config, home),
    shell: false,
    stdio: ['ignore', 'ignore', 'pipe'],
  });
  // stderr boşaltılır; sağlayıcı sırları veya promptlar loga kopyalanmaz.
  child.stderr?.resume();
  let exited = false;
  child.on('close', () => {
    exited = true;
  });
  child.on('error', () => {
    exited = true;
  });
  const stop = async () => {
    if (exited) return;
    child.kill('SIGTERM');
  };
  const origin = `http://127.0.0.1:${port}`;
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline && !exited) {
    try {
      const response = await request(`${origin}/health`);
      if (response.ok) return { baseUrl: `${origin}/v1`, close: stop };
    } catch {
      // Geçit henüz dinlemiyor; kısa bekleyip yeniden dene.
    }
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }
  await stop();
  throw new Error(
    exited
      ? 'Fusion geçidi başlarken kapandı.'
      : `Fusion geçidi ${Math.round(timeoutMs / 1000)} sn içinde açılmadı.`,
  );
}

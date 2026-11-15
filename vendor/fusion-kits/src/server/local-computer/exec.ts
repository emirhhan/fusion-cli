import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir, realpath } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { OperationError } from './errors.js';

const SANDBOX_EXEC = '/usr/bin/sandbox-exec';
export const MAX_OUTPUT_BYTES = 65_536;

/**
 * Önce her yere yazmayı yasaklar, sonra yalnız Kit klasörüne ve geçici
 * dizinlere izin verir. Veri dizini (diğer Kit'ler, veritabanı) ve kullanıcının ev
 * klasörü (anahtarlar, ayarlar, belgeler) okumaya da kapalıdır.
 */
export const SANDBOX_PROFILE = `(version 1)
(allow default)
(deny file-write* (subpath "/"))
(allow file-write* (subpath (param "ROOT")) (subpath "/private/tmp") (subpath "/dev"))
(deny file-read* file-write* (subpath (param "DATA")))
(deny file-read* (subpath (param "HOME")))
(allow file-read* file-write* (subpath (param "ROOT")))`;

export function sandboxAvailable() {
  return process.platform === 'darwin' && existsSync(SANDBOX_EXEC);
}

function collect(limit: number) {
  const chunks: Buffer[] = [];
  let size = 0;
  let truncated = false;
  return {
    push(chunk: Buffer) {
      const room = limit - size;
      if (room <= 0) return void (truncated = true);
      if (chunk.length > room) truncated = true;
      const part = chunk.subarray(0, room);
      chunks.push(part);
      size += part.length;
    },
    text: () => Buffer.concat(chunks).toString('utf8'),
    truncated: () => truncated,
  };
}

export async function runSandboxed(
  root: string,
  dataDir: string,
  command: string,
  timeoutMs: number,
) {
  if (!sandboxAvailable())
    throw new OperationError(
      'Komut çalıştırma yalnızca macOS’ta sandbox-exec ile desteklenir; bu sistemde klasör dışına yazmayı engelleyen yalıtım olmadığı için komut reddedildi.',
    );
  // Sandbox yolları gerçek (sembolik bağsız) yol ister; aksi halde kural eşleşmez.
  const data = await realpath(dataDir);
  root = await realpath(root);
  const tmp = join(root, '.tmp');
  await mkdir(tmp, { recursive: true });
  const child = spawn(
    SANDBOX_EXEC,
    [
      '-D',
      `ROOT=${root}`,
      '-D',
      `DATA=${data}`,
      '-D',
      `HOME=${await realpath(homedir())}`,
      '-p',
      SANDBOX_PROFILE,
      '/bin/sh',
      '-c',
      command,
    ],
    {
      cwd: root,
      detached: true,
      stdio: ['ignore', 'pipe', 'pipe'],
      // Sunucunun gizli anahtarları alt sürece geçmez.
      env: {
        PATH: '/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
        HOME: root,
        TMPDIR: tmp,
        LANG: 'en_US.UTF-8',
      },
    },
  );
  const out = collect(MAX_OUTPUT_BYTES);
  const err = collect(MAX_OUTPUT_BYTES);
  child.stdout.on('data', out.push);
  child.stderr.on('data', err.push);
  let timedOut = false;
  const kill = () => {
    try {
      if (child.pid) process.kill(-child.pid, 'SIGKILL');
    } catch {
      /* süreç zaten bitti */
    }
  };
  const timer = setTimeout(() => {
    timedOut = true;
    kill();
  }, timeoutMs);
  const code = await new Promise<number | null>((resolve, reject) => {
    child.once('error', reject);
    child.once('close', resolve);
  }).finally(() => {
    clearTimeout(timer);
    kill();
  });
  return {
    exitCode: code ?? -1,
    stdout: out.text(),
    stderr: err.text(),
    timedOut,
    truncated: out.truncated() || err.truncated(),
  };
}

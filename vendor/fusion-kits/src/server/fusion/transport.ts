import { spawn } from 'node:child_process';
import { StringDecoder } from 'node:string_decoder';
import { mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
import type { FusionConfig } from './config.js';

export interface FusionTransport {
  send(line: string): void;
  subscribe(listener: (line: string) => void): () => void;
  onFailure(listener: (error: Error) => void): () => void;
  close(): Promise<void>;
}

/** UTF-8 parçaları ve CRLF satırları kayıpsız, sınırlı şekilde birleştirilir. */
export class LineDecoder {
  private decoder = new StringDecoder('utf8');
  private buffer = '';
  constructor(
    private limit: number,
    private receive: (line: string) => void,
  ) {}
  push(chunk: Buffer) {
    this.buffer += this.decoder.write(chunk);
    let index: number;
    while ((index = this.buffer.indexOf('\n')) >= 0) {
      const line = this.buffer.slice(0, index).replace(/\r$/, '');
      this.buffer = this.buffer.slice(index + 1);
      if (Buffer.byteLength(line) > this.limit)
        throw new Error('Fusion protokol satırı sınırı aşıldı.');
      if (line.trim()) this.receive(line);
    }
    if (Buffer.byteLength(this.buffer) > this.limit)
      throw new Error('Fusion protokol satırı sınırı aşıldı.');
  }
}

/** Fusion alt süreç ortamı: Kits servis anahtarları geçirilmez, çekirdek ayrı evini kullanır. */
export function fusionEnv(
  config: FusionConfig,
  home: string,
): Record<string, string> {
  const env: Record<string, string> = {};
  for (const key of ['PATH', 'TMPDIR', 'SystemRoot', 'WINDIR', 'LANG'])
    if (process.env[key]) env[key] = process.env[key]!;
  const userHome = config.userConfigHome ?? config.home;
  env.HOME = userHome;
  env.USERPROFILE = userHome;
  env.XDG_CONFIG_HOME = join(userHome, '.config');
  env.APPDATA = join(userHome, '.config');
  env.XDG_DATA_HOME = join(home, 'data');
  env.LOCALAPPDATA = join(home, 'data');
  env.FUSION_HOME = config.home;
  env.FUSION_MEMORY_DIR = join(home, 'memory');
  env.PYTHONUTF8 = '1';
  return env;
}

export function processTransport(
  config: FusionConfig,
  threadId: string,
): FusionTransport {
  const identity = createHash('sha256').update(threadId).digest('hex');
  const home = join(config.home, identity);
  mkdirSync(home, { recursive: true });
  const listeners = new Set<(line: string) => void>();
  const failures = new Set<(error: Error) => void>();
  let failure: Error | undefined;
  let closed = false;
  let exited = false;
  let closing: Promise<void> | undefined;
  const env = fusionEnv(config, home);
  const child = spawn(config.command, config.args, {
    cwd: config.root,
    env,
    shell: false,
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  const fail = (error: Error) => {
    if (failure || closed) return;
    failure = error;
    failures.forEach((listener) => listener(error));
  };
  const decoder = new LineDecoder(config.maxLineBytes, (line) =>
    listeners.forEach((listener) => listener(line)),
  );
  child.stdout.on('data', (chunk: Buffer) => {
    try {
      decoder.push(chunk);
    } catch (error) {
      fail(
        error instanceof Error ? error : new Error('Fusion protokol hatası.'),
      );
      child.kill();
    }
  });
  // stderr boşaltılır; sağlayıcı sırları veya promptlar loga kopyalanmaz.
  child.stderr.resume();
  child.on('error', () =>
    fail(
      new Error('Fusion süreci başlatılamadı; komut ve dizinleri denetleyin.'),
    ),
  );
  child.stdin.on('error', () =>
    fail(new Error('Fusion protokol bağlantısına yazılamadı.')),
  );
  child.on('close', () => {
    exited = true;
    fail(new Error('Fusion süreci kapandı.'));
  });
  return {
    send(line) {
      if (closed || failure || exited)
        throw failure ?? new Error('Fusion bağlantısı kapandı.');
      if (Buffer.byteLength(line) > config.maxLineBytes)
        throw new Error('Fusion istek sınırı aşıldı.');
      child.stdin.write(line + '\n');
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    onFailure(listener) {
      failures.add(listener);
      if (failure) listener(failure);
      return () => failures.delete(listener);
    },
    close() {
      return (closing ??= (async () => {
        closed = true;
        listeners.clear();
        failures.clear();
        if (exited) return;
        await new Promise<void>((resolve) => {
          let escalation: ReturnType<typeof setTimeout>;
          const timer = setTimeout(() => {
            child.kill('SIGTERM');
            escalation = setTimeout(
              () => child.kill('SIGKILL'),
              config.shutdownTimeoutMs,
            );
          }, config.shutdownTimeoutMs);
          child.once('close', () => {
            clearTimeout(timer);
            clearTimeout(escalation);
            resolve();
          });
          child.stdin.end();
        });
      })());
    },
  };
}

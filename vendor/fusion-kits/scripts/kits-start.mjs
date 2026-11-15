import { existsSync, copyFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawn, spawnSync } from 'node:child_process';
import process from 'node:process';

export const projectRoot = resolve(
  dirname(fileURLToPath(import.meta.url)),
  '..',
);
export function assertRuntime(version = process.versions.node) {
  if (Number(version.split('.')[0]) < 24)
    throw new Error(
      'Fusion Kits için Node.js 24 veya üzeri gerekli. npm run kits:start komutunu kullanın.',
    );
}
export function launchSettings(env) {
  const port = Number(env.PORT || 4410);
  if (!Number.isInteger(port) || port < 1 || port > 65535)
    throw new Error('PORT 1–65535 arasında bir tam sayı olmalı.');
  const host = env.HOST || '127.0.0.1';
  if (
    !['127.0.0.1', 'localhost', '::1'].includes(host) &&
    (!env.OWNER_TOKEN || env.OWNER_TOKEN.length < 24)
  )
    throw new Error('Harici HOST için en az 24 karakter OWNER_TOKEN gerekli.');
  return {
    ...env,
    HOST: host,
    PORT: String(port),
    DATABASE_PATH: env.DATABASE_PATH || 'data/fusion-kits.sqlite',
    OWNER_ID: env.OWNER_ID || 'fusion-kits-owner',
    COMPUTER_NAMESPACE: env.COMPUTER_NAMESPACE || 'fusion-kits',
    KITS_API_TARGET: `http://${host === '::1' ? '[::1]' : '127.0.0.1'}:${port}`,
  };
}
export function runNpm(args, env = process.env, root = projectRoot) {
  const cli = process.env.npm_execpath;
  if (!cli)
    throw new Error(
      'Bu işlemi npm run kits:start veya npm run kits:check üzerinden çalıştırın.',
    );
  const result = spawnSync(process.execPath, [cli, ...args], {
    cwd: root,
    env,
    stdio: 'inherit',
  });
  if (result.error) throw result.error;
  if (result.status !== 0)
    throw new Error(`npm ${args.join(' ')} başarısız: ${result.status}`);
}
function main() {
  assertRuntime();
  if (existsSync(resolve(projectRoot, '.env')))
    process.loadEnvFile(resolve(projectRoot, '.env'));
  const env = launchSettings(process.env);
  if (process.argv.includes('--check')) {
    for (const file of [
      'package-lock.json',
      'src/server/index.ts',
      'public/dots/blue.png',
      'LICENSE',
    ])
      if (!existsSync(resolve(projectRoot, file)))
        throw new Error(`Paket eksik: ${file}`);
    console.log(
      `Fusion Kits hazır. Node ${process.versions.node}; ${env.KITS_API_TARGET}; depo ${env.DATABASE_PATH}`,
    );
    return;
  }
  if (!existsSync(resolve(projectRoot, '.env')))
    copyFileSync(
      resolve(projectRoot, '.env.example'),
      resolve(projectRoot, '.env'),
    );
  if (!existsSync(resolve(projectRoot, 'node_modules/.package-lock.json')))
    runNpm(['ci'], env);
  const dev = process.argv.includes('--dev');
  if (
    !dev &&
    (!existsSync(resolve(projectRoot, 'dist/server/server/index.js')) ||
      process.argv.includes('--build'))
  )
    runNpm(['run', 'build'], env);
  console.log(
    `Fusion Kits: ${dev ? 'http://127.0.0.1:4413' : env.KITS_API_TARGET}`,
  );
  const child = dev
    ? spawn(process.execPath, [process.env.npm_execpath, 'run', 'dev'], {
        cwd: projectRoot,
        env,
        stdio: 'inherit',
      })
    : spawn(
        process.execPath,
        ['--env-file-if-exists=.env', 'dist/server/server/index.js'],
        { cwd: projectRoot, env, stdio: 'inherit' },
      );
  child.on('error', (error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
  child.on('exit', (code) => {
    process.exitCode = code ?? 1;
  });
  for (const signal of ['SIGINT', 'SIGTERM'])
    process.on(signal, () => child.kill(signal));
}
if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
  try {
    main();
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}

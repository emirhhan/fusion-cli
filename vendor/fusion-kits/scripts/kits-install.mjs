// Kits paketini Fusion masaüstü uygulamasının aradığı yere kurar:
//   <veri>/fusion-cli/kits/app   (paket)
//   <veri>/fusion-cli/kits/.env  (model ayarı; yoksa bu klasördeki .env kopyalanır)
// Sır değerleri okunmaz ya da yazdırılmaz; dosya olduğu gibi kopyalanır.
import { chmodSync, copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import process from 'node:process';
import { projectRoot } from './kits-start.mjs';

const dataRoot =
  process.platform === 'win32'
    ? (process.env.LOCALAPPDATA ?? resolve(homedir(), 'AppData/Local'))
    : resolve(homedir(), '.local/share');
const kitsHome = resolve(dataRoot, 'fusion-cli/kits');
mkdirSync(kitsHome, { recursive: true });
const bundled = spawnSync(
  process.execPath,
  [resolve(projectRoot, 'scripts/kits-bundle.mjs'), resolve(kitsHome, 'app')],
  { cwd: projectRoot, stdio: 'inherit' },
);
if (bundled.status !== 0) process.exit(bundled.status ?? 1);
const source = resolve(projectRoot, '.env');
const target = resolve(kitsHome, '.env');
if (!existsSync(target) && existsSync(source)) {
  copyFileSync(source, target);
  chmodSync(target, 0o600);
  console.log(`Model ayarı kopyalandı: ${target}`);
} else if (!existsSync(target)) {
  console.log(
    `Model ayarı yok. ${target} dosyasına OPENAI_* ayarlarını ekleyin.`,
  );
}
console.log(`Kits kuruldu: ${kitsHome}`);

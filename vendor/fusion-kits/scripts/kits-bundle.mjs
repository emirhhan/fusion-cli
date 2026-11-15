// Fusion masaüstü uygulamasına gömülecek taşınabilir Kits paketi üretir:
// sunucu tek dosyaya derlenir (node_modules gerekmez), arayüz yanına kopyalanır.
// Çıktı düzeni çalışma kopyasıyla aynıdır: dist/server/server/index.js + dist/client.
import {
  cpSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { resolve } from 'node:path';
import process from 'node:process';
import { build } from 'esbuild';
import { projectRoot } from './kits-start.mjs';

const PLAYWRIGHT_PACKAGES = ['playwright', 'playwright-core'];
const output = resolve(projectRoot, process.argv[2] ?? 'bundle');
rmSync(output, { recursive: true, force: true });
mkdirSync(resolve(output, 'dist/server/server'), { recursive: true });
const result = await build({
  entryPoints: [resolve(projectRoot, 'src/server/index.ts')],
  outfile: resolve(output, 'dist/server/server/index.js'),
  bundle: true,
  platform: 'node',
  format: 'esm',
  target: 'node24',
  minify: false,
  legalComments: 'none',
  logLevel: 'warning',
  metafile: true,
  // Playwright sürücüsünü diskten okur, tek dosyaya derlenemez (chromium-bidi
  // çözülemiyordu); paketin yanına node_modules olarak kopyalanır.
  external: PLAYWRIGHT_PACKAGES,
  // Paketlenen CommonJS bağımlılıkları `require` ve `__dirname` bekler.
  banner: {
    js: "import { createRequire as __kitsRequire } from 'node:module'; import { fileURLToPath as __kitsPath } from 'node:url'; import { dirname as __kitsDir } from 'node:path'; const require = __kitsRequire(import.meta.url); const __filename = __kitsPath(import.meta.url); const __dirname = __kitsDir(__filename);",
  },
});
cpSync(resolve(projectRoot, 'dist/client'), resolve(output, 'dist/client'), {
  recursive: true,
});
for (const name of PLAYWRIGHT_PACKAGES)
  cpSync(
    resolve(projectRoot, 'node_modules', name),
    resolve(output, 'node_modules', name),
    { recursive: true, dereference: true },
  );
for (const file of ['LICENSE', 'LICENSE.fusion', '.env.example'])
  cpSync(resolve(projectRoot, file), resolve(output, file));
writeFileSync(
  resolve(output, 'package.json'),
  `${JSON.stringify({ name: 'fusion-kits-bundle', private: true, type: 'module' }, null, 2)}\n`,
);
// channels-core çalışırken kendi `../package.json` dosyasını okur; tek dosyaya
// derlenince bu yol paketin `dist/server/package.json` dosyasına denk gelir.
const channels = JSON.parse(
  readFileSync(
    resolve(projectRoot, 'node_modules/@copilotkit/channels-core/package.json'),
    'utf8',
  ),
);
writeFileSync(
  resolve(output, 'dist/server/package.json'),
  `${JSON.stringify({ name: channels.name, version: channels.version, type: 'module' }, null, 2)}\n`,
);
const bytes = Object.values(result.metafile.outputs).reduce(
  (total, item) => total + item.bytes,
  0,
);
console.log(`Kits paketi: ${output} (sunucu ${(bytes / 1e6).toFixed(1)} MB)`);

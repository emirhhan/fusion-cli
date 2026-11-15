import { chromium } from 'playwright';
import {
  mkdtempSync,
  mkdirSync,
  symlinkSync,
  copyFileSync,
  readFileSync,
  writeFileSync,
  rmSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawnSync, spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import { createHash } from 'node:crypto';
import process from 'node:process';
import { WorkspaceStore } from '../src/server/workspace.ts';
import { projectRoot, assertRuntime } from './kits-start.mjs';
assertRuntime();
const upstream = JSON.parse(
  readFileSync(join(projectRoot, 'handoff/upstream.json'), 'utf8'),
);
const temporary = mkdtempSync(join(tmpdir(), 'fusion-kits-reference-'));
const original = join(temporary, 'upstream');
mkdirSync(original);
const output = join(projectRoot, 'handoff/parity');
mkdirSync(output, { recursive: true });
const children = [];
let browser;
const report = {
  upstream: upstream.commit,
  mode: 'real-upstream-and-kits-local-ui-no-live-model',
  unchangedComponents: [],
  screenshots: [],
  checks: [],
  pixelDifferences: {},
  error: null,
};
try {
  const archive = spawnSync('git', ['archive', upstream.commit], {
    cwd: projectRoot,
    maxBuffer: 64 * 1024 * 1024,
  });
  if (archive.status !== 0)
    throw new Error(
      'Sabit upstream Git kaynağı gerekli; bu kontrol geliştirme checkout içinde çalışır.',
    );
  const unpack = spawnSync('tar', ['-x', '-C', original], {
    input: archive.stdout,
  });
  if (unpack.status !== 0) throw new Error('Upstream arşivi açılamadı.');
  symlinkSync(
    join(projectRoot, 'node_modules'),
    join(original, 'node_modules'),
    'dir',
  );
  const build = spawnSync(
    process.execPath,
    [process.env.npm_execpath, 'run', 'build'],
    { cwd: original, env: process.env, encoding: 'utf8', timeout: 120000 },
  );
  writeFileSync(
    join(output, 'reference-build.log'),
    build.stdout + build.stderr,
  );
  if (build.status !== 0)
    throw new Error('Sabit upstream referansı derlenemedi.');
  for (const path of [
    'src/client/SpaceLibrary.tsx',
    'src/client/editor.css',
    'src/server/pages.ts',
    'src/server/page-tools.ts',
    'src/server/slack-channel.ts',
  ]) {
    const digest = (file) =>
      createHash('sha256').update(readFileSync(file)).digest('hex');
    if (digest(join(original, path)) !== digest(join(projectRoot, path)))
      throw new Error(`Beklenmeyen çekirdek bileşen farkı: ${path}`);
    report.unchangedComponents.push(path);
  }
  const seed = join(temporary, 'seed.sqlite');
  const workspace = new WorkspaceStore(seed, 'reference-fixture');
  const dot = workspace.dots()[0];
  workspace.updateDot(dot.id, {
    ...dot,
    name: 'Araştırmacı',
    instructions: 'Görsel referans verisi.',
  });
  const space = workspace.createSpace(
    'Fusion çalışma alanı',
    'Referans karşılaştırması',
  );
  workspace.pages.create(space.id, {
    title: 'Aynı belge',
    content: '# Aynı belge\n\nÖzgün editör ve belge yolu.',
  });
  workspace.close();
  browser = await chromium.launch({ headless: true });
  const captures = {};
  for (const [name, cwd, port] of [
    ['upstream', original, 4470],
    ['kits', projectRoot, 4471],
  ]) {
    const database = join(temporary, `${name}.sqlite`);
    copyFileSync(seed, database);
    const base = `http://127.0.0.1:${port}`;
    const env = {
      PATH: process.env.PATH,
      HOME: join(temporary, 'home'),
      PORT: String(port),
      HOST: '127.0.0.1',
      DATABASE_PATH: database,
      OWNER_ID: 'reference-fixture',
      OWNER_TOKEN: '',
      APP_ORIGIN: base,
      WEB_SEARCH_PROVIDER: 'disabled',
      INTELLIGENCE_API_KEY: '',
      OPENAI_API_KEY: '',
      OPENAI_MODEL: '',
      VOICE_API_KEY: '',
      VOICE_MODEL: '',
      SLACK_CHANNEL_NAME: '',
      COMPUTER_SUPERVISOR_URL: '',
    };
    const child = spawn(process.execPath, ['dist/server/server/index.js'], {
      cwd,
      env,
      stdio: 'ignore',
    });
    children.push(child);
    let ready = false;
    for (let attempt = 0; attempt < 100; attempt++) {
      try {
        const response = await fetch(`${base}/api/workspace`);
        if (response.ok) {
          ready = true;
          break;
        }
      } catch {
        /* İzole server başlangıcında henüz bağlantı yok. */
      }
      await delay(100);
    }
    if (!ready) throw new Error(`${name} referans sunucusu başlayamadı.`);
    const page = await browser.newPage({
      viewport: { width: 1440, height: 1000 },
    });
    await page.goto(base);
    await page.locator('.sidebar').waitFor();
    await page.screenshot({
      path: join(output, `${name}-reference-home.png`),
      animations: 'disabled',
    });
    report.screenshots.push(`${name}-reference-home.png`);
    await page.goto(`${base}/#/spaces/${space.id}`);
    await page.locator('.space-library').waitFor();
    const titles = await page.locator('.library-page-card').allTextContents();
    if (!titles.some((title) => title.includes('Aynı belge')))
      throw new Error('Aynı veride belge görünmedi.');
    captures[name] = (
      await page.screenshot({
        path: join(output, `${name}-reference-library.png`),
        animations: 'disabled',
      })
    ).toString('base64');
    report.screenshots.push(`${name}-reference-library.png`);
    await page.close();
  }
  const analysis = await browser.newPage();
  report.pixelDifferences = await analysis.evaluate(
    async ({ before, after }) => {
      const pixels = async (encoded) => {
        const img = new globalThis.Image();
        img.src = `data:image/png;base64,${encoded}`;
        await img.decode();
        const canvas = globalThis.document.createElement('canvas');
        canvas.width = img.width;
        canvas.height = img.height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0);
        return ctx.getImageData(0, 0, canvas.width, canvas.height);
      };
      const a = await pixels(before),
        b = await pixels(after);
      let changed = 0;
      for (let i = 0; i < a.data.length; i += 4) {
        if (
          a.data[i] !== b.data[i] ||
          a.data[i + 1] !== b.data[i + 1] ||
          a.data[i + 2] !== b.data[i + 2]
        )
          changed++;
      }
      return {
        width: a.width,
        height: a.height,
        changedPixels: changed,
        ratio: changed / (a.width * a.height),
        interpretation:
          'Menü ölçüsü, Fusion teması ve marka değişimleri dahil gözlenen tam ekran farkı; birebir piksel eşliği iddiası değildir.',
      };
    },
    { before: captures.upstream, after: captures.kits },
  );
  report.checks.push(
    'same-seeded-data-on-both-real-apps',
    'unchanged-core-component-hashes',
    'recorded-full-screen-pixel-difference',
  );
} catch (error) {
  report.error = error.message;
  process.exitCode = 1;
} finally {
  await browser?.close();
  for (const child of children) {
    if (child.exitCode === null) {
      await new Promise((resolve) => {
        const kill = setTimeout(() => child.kill('SIGKILL'), 2000);
        child.once('close', () => {
          clearTimeout(kill);
          resolve();
        });
        child.kill('SIGTERM');
      });
    }
  }
  rmSync(temporary, { recursive: true, force: true });
  writeFileSync(
    join(output, 'reference-report.json'),
    JSON.stringify(report, null, 2) + '\n',
  );
  console.log(JSON.stringify(report, null, 2));
}

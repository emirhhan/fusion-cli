import { checkMobileLayout } from './kits-mobile-layout-check.mjs';
import { checkAssets } from './kits-assets-check.mjs';
import { checkConversationNavigation } from './kits-conversation-check.mjs';
import { House, Clock3, Library, Images, Sparkles } from 'lucide-react';
import { chromium } from 'playwright';
import {
  mkdtempSync,
  mkdirSync,
  rmSync,
  writeFileSync,
  readFileSync,
  openSync,
  closeSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import { renderToStaticMarkup } from 'react-dom/server';
import { createElement } from 'react';
import process from 'node:process';
import { WorkspaceStore } from '../src/server/workspace.ts';
import { fusionNavigation } from '../src/integration/fusion-kits.ts';
import { CallView } from '../src/client/CallView.tsx';
import { FusionCard } from '../src/client/FusionCard.tsx';
import { assertRuntime, projectRoot } from './kits-start.mjs';
import { checkPageConflict } from './kits-page-conflict-check.mjs';

assertRuntime();
const out = resolve(
  process.env.KITS_VISUAL_OUT || resolve(projectRoot, 'handoff/parity'),
);
mkdirSync(out, { recursive: true });
const temporary = mkdtempSync(join(tmpdir(), 'fusion-kits-visual-'));
const database = join(temporary, 'workspace.sqlite');
const workspace = new WorkspaceStore(database, 'visual-fixture');
const first = workspace.dots()[0];
workspace.updateDot(first.id, {
  ...first,
  name: 'Araştırmacı',
  instructions:
    'Görsel test verisi. Kaynakları incele, kanıtları karşılaştır ve bulguları belgeye dönüştür.',
});
for (const name of ['Yazar', 'Geliştirici', 'Planlayıcı'])
  workspace.createDot(
    first.spaceId,
    name,
    `${name} uzmanı. Görsel test verisi.`,
    true,
    true,
  );
const space = workspace.createSpace(
  'Fusion çalışma alanı',
  'Görsel test verisi · gerçek servisler bağlı değildir.',
);
const document = workspace.pages.create(space.id, {
  title: 'Fusion Kits çalışma notları',
  content:
    '# Birlikte çalışan uzmanlar\n\nFusion Kits, kalıcı sohbetleri ve belgeleri aynı çalışma alanında birleştirir.\n\n## Çalışma akışı\n\n- Araştır ve kaynakları karşılaştır\n- Taslağı gözden geçir\n- Onayla ve belgeye kaydet\n\n## Bağlantılar\n\nFusion çekirdeği, ses ve bilgisayar servisleri ayrı yapılandırılır.',
});
workspace.pages.create(space.id, {
  title: 'Ürün taslağı',
  content:
    '# Ürün taslağı\n\nBelge editörü ve alt sayfalar gerçek yerel API üzerinden çalışır.',
});
workspace.pages.create(space.id, {
  title: 'Kabul kontrolü',
  content:
    '# Kabul kontrolü\n\n- [ ] Canlı model\n- [ ] Ses\n- [ ] Slack\n- [ ] Bilgisayar',
});
const measuredLibrarySize = Number(process.env.KITS_VISUAL_LIBRARY_SIZE || 0);
if (
  !Number.isInteger(measuredLibrarySize) ||
  measuredLibrarySize < 0 ||
  measuredLibrarySize > 10000
)
  throw new Error('Kitaplık ölçüm boyutu 0–10000 olmalı.');
for (let index = 0; index < measuredLibrarySize; index++)
  workspace.pages.create(space.id, {
    title: `Ölçüm belgesi ${String(index).padStart(5, '0')}`,
    content: `# Ölçüm belgesi ${index}\n\nArama ve ilk çizim için yerel veri; canlı model çalıştırılmaz.`,
  });
workspace.close();
const port = Number(process.env.KITS_VISUAL_PORT || 4460);
const base = `http://127.0.0.1:${port}`;
const env = {
  ...process.env,
  HOST: '127.0.0.1',
  PORT: String(port),
  DATABASE_PATH: database,
  OWNER_ID: 'visual-fixture',
  OWNER_TOKEN: '',
  APP_ORIGIN: base,
  KITS_HOST_ORIGINS: JSON.stringify([base]),
  INTELLIGENCE_API_KEY: '',
  OPENAI_API_KEY: '',
  OPENAI_MODEL: '',
  VOICE_API_KEY: '',
  VOICE_MODEL: '',
  SLACK_CHANNEL_NAME: '',
  SLACK_TEAM_ID: '',
  SLACK_USER_IDS: '',
  COMPUTER_SUPERVISOR_URL: '',
  COMPUTER_SUPERVISOR_TOKEN: '',
  COMPUTER_TOKEN: '',
  WEB_SEARCH_PROVIDER: 'disabled',
};
for (const key of Object.keys(env))
  if (key.startsWith('FUSION_')) delete env[key];
const logFd = openSync(join(out, 'server.log'), 'w');
const server = spawn(
  process.execPath,
  process.env.KITS_VISUAL_BUNDLE
    ? ['dist/server/server/index.js']
    : ['--import', 'tsx', 'src/server/index.ts'],
  {
    cwd: process.env.KITS_VISUAL_BUNDLE || projectRoot,
    env,
    stdio: ['ignore', logFd, logFd],
  },
);
let browser;
const report = {
  mode: 'local-ui-and-labelled-fixtures',
  screenshots: [],
  checks: [],
  pageErrors: [],
};
try {
  let ready = false;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (server.exitCode !== null)
      throw new Error('Görsel test sunucusu başlayamadı.');
    try {
      const response = await fetch(`${base}/api/workspace`);
      const body = await response.json();
      if (body.spaces?.some((item) => item.id === space.id)) {
        ready = true;
        break;
      }
    } catch {
      /* Başlangıç boyunca bağlantı henüz hazır olmayabilir. */
    }
    await delay(100);
  }
  if (!ready) throw new Error('Görsel test sunucusu zamanında hazır olmadı.');
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1,
  });
  page.on('pageerror', (error) => report.pageErrors.push(error.message));
  const badge = async (
    label = 'YEREL ARAYÜZ TESTİ · CANLI MODEL BAĞLI DEĞİL',
  ) =>
    page.evaluate((text) => {
      document.querySelector('#test-badge')?.remove();
      const element = document.createElement('div');
      element.id = 'test-badge';
      element.textContent = text;
      element.style.cssText =
        'position:fixed;bottom:8px;right:8px;z-index:9999;background:#0b0a0d;color:#22d3ee;padding:6px 10px;border-radius:6px;font:10px system-ui;pointer-events:none';
      document.body.append(element);
    }, label);
  const screenshot = async (name) => {
    await page.evaluate((theme) => {
      if (theme === 'dark') document.documentElement.dataset.theme = 'dark';
    }, process.env.KITS_VISUAL_THEME);
    await badge();
    await page.evaluate(async () => {
      await document.fonts.ready;
    });
    await page.screenshot({
      path: join(out, `${name}.png`),
      animations: 'disabled',
      fullPage: false,
    });
    report.screenshots.push(`${name}.png`);
  };
  await page.goto(base);
  await page
    .getByRole('button', { name: 'Fusion Kits', exact: true })
    .waitFor();
  if (process.env.KITS_VISUAL_CONVERSATION === '1') {
    report.checks.push(await checkConversationNavigation(page, base));
    report.checks.push(await checkConversationNavigation(page, base, true));
  }
  await screenshot('kits-home-desktop');
  const sidebar = await page.locator('#workspace-sidebar').boundingBox();
  if (sidebar.x !== 0 || sidebar.width !== 260)
    throw new Error(`Fusion menü ölçüleri yanlış: ${JSON.stringify(sidebar)}`);
  report.checks.push('desktop-menu-left-0-width-260');
  await page.goto(`${base}/#/spaces/${space.id}`);
  await page.getByRole('heading', { name: space.name, exact: true }).waitFor();
  if (measuredLibrarySize) {
    const expected = measuredLibrarySize + 3;
    const firstRender = Math.min(expected, 50);
    await page.waitForFunction(
      (size) =>
        globalThis.document.querySelectorAll('.library-pages > button')
          .length === size,
      firstRender,
    );
    const initial = await page.evaluate(() => ({
      elapsedMs: globalThis.performance.now(),
      cards: globalThis.document.querySelectorAll('.library-pages > button')
        .length,
      nodes: globalThis.document.querySelectorAll('*').length,
    }));
    if (expected > 50) {
      await page
        .getByRole('button', { name: '50 sayfa daha göster', exact: true })
        .click();
      await page.waitForFunction(
        () =>
          globalThis.document.querySelectorAll('.library-pages > button')
            .length === 100,
      );
    }
    if (expected > 50)
      await page.waitForFunction(
        () =>
          globalThis.document.querySelectorAll('.library-page-card')[50] ===
          globalThis.document.activeElement,
      );
    const before = Date.now();
    await page
      .getByRole('textbox', { name: 'Sayfalarda ara', exact: true })
      .fill('Kabul kontrolü');
    await page.waitForFunction(
      () =>
        globalThis.document.querySelectorAll('.library-pages > button')
          .length === 1,
    );
    report.libraryMeasurement = {
      pages: expected,
      initial,
      searchWallMs: Date.now() - before,
      baselineOnly: true,
      conditions:
        'local-headless-ui-no-model; concurrent acceptance run, not isolated benchmark',
    };
    await page
      .getByRole('textbox', { name: 'Sayfalarda ara', exact: true })
      .fill('');
    await page.waitForFunction(
      (size) =>
        globalThis.document.querySelectorAll('.library-pages > button')
          .length === size,
      firstRender,
    );
  }
  await screenshot('kits-library-desktop');
  await page
    .getByRole('button', { name: 'Liste görünümü', exact: true })
    .click();
  await screenshot('kits-library-list');
  await page.goto(`${base}/#/spaces/${space.id}/pages/${document.id}`);
  await page
    .getByRole('textbox', { name: 'Sayfa başlığı', exact: true })
    .waitFor();
  await page.locator('[contenteditable="true"]').waitFor();
  await screenshot('kits-editor-desktop');
  await page
    .getByRole('textbox', { name: 'Sayfa başlığı', exact: true })
    .fill('Fusion Kits kayıt kontrolü');
  let saved = false;
  for (let attempt = 0; attempt < 40; attempt++) {
    const response = await fetch(
      `${base}/api/spaces/${space.id}/pages/${document.id}`,
    );
    const data = await response.json();
    if (data.title === 'Fusion Kits kayıt kontrolü') {
      saved = true;
      break;
    }
    await delay(100);
  }
  if (!saved) throw new Error('Gerçek API otomatik kayıt kontrolü başarısız.');
  await page.reload();
  await page
    .getByRole('textbox', { name: 'Sayfa başlığı', exact: true })
    .waitFor();
  if (
    (await page
      .getByRole('textbox', { name: 'Sayfa başlığı', exact: true })
      .inputValue()) !== 'Fusion Kits kayıt kontrolü'
  )
    throw new Error('Yeniden yükleme kaydı korumadı.');
  report.checks.push('real-api-page-autosave-and-reload');
  if (process.env.KITS_VISUAL_CONFLICT === '1')
    report.checks.push(
      await checkPageConflict(page, base, space.id, document.id, screenshot),
    );
  await page
    .getByRole('button', { name: 'Araştırmacı ayarlarını düzenle' })
    .click();
  await page.getByRole('dialog').waitFor();
  await screenshot('kits-settings-desktop');
  await page.getByRole('button', { name: 'Pencereyi kapat' }).click();
  await page.getByRole('button', { name: 'Bilgisayarı göster' }).click();
  await page.getByLabel('Araştırmacı bilgisayarı', { exact: true }).waitFor();
  await screenshot('kits-computer-setup');
  if (process.env.KITS_VISUAL_LAYOUT === '1')
    report.checks.push(
      await checkMobileLayout(page, base, space.id, document.id, screenshot),
    );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(base);
  await page.getByRole('button', { name: 'Menüyü aç' }).click();
  await page.locator('#workspace-sidebar.open').waitFor();
  await screenshot('kits-menu-mobile');
  await page
    .getByRole('button', { name: 'Menüyü kapat' })
    .click({ position: { x: 375, y: 400 } });
  await screenshot('kits-home-mobile');
  if (
    await page.evaluate(
      () => document.documentElement.scrollWidth > globalThis.innerWidth,
    )
  )
    throw new Error('Dar ekranda yatay taşma var.');
  report.checks.push('mobile-menu-and-no-horizontal-overflow');
  await page.setViewportSize({ width: 1440, height: 1000 });
  const index = readFileSync(
    resolve(projectRoot, 'dist/client/index.html'),
    'utf8',
  );
  const css = [...index.matchAll(/href="([^"]+\.css)"/g)]
    .map((match) => `<link rel="stylesheet" href="${base}${match[1]}">`)
    .join('');
  const fixture = async (markup, name) => {
    await page.goto(base);
    await page.setContent(
      `<html><head><base href="${base}/">${css}</head><body><div class="fusion-kits">${markup}</div></body></html>`,
    );
    await page
      .locator('img')
      .evaluateAll((images) =>
        Promise.all(images.map((image) => image.decode().catch(() => {}))),
      );
    await page.evaluate((theme) => {
      if (theme === 'dark') document.documentElement.dataset.theme = 'dark';
    }, process.env.KITS_VISUAL_THEME);
    await badge('BİLEŞEN GÖRSEL TESTİ · CANLI GÖRÜŞME / GÖREV DEĞİLDİR');
    await page.screenshot({
      path: join(out, `${name}.png`),
      animations: 'disabled',
    });
    report.screenshots.push(`${name}.png`);
  };
  const dot = { ...first, name: 'Araştırmacı' };
  await fixture(
    renderToStaticMarkup(
      createElement(CallView, {
        dot,
        voice: {
          status: 'active',
          phase: 'listening',
          startedAt: Date.now() - 65000,
          muted: false,
          speakerMuted: false,
          userCaption: 'Fusion Kits arayüzünü inceliyoruz.',
          caption: 'Hazırım. Belgeler ve görevler aynı çalışma alanında.',
          error: '',
          toggleMute() {},
          toggleSpeaker() {},
          async end() {},
        },
      }),
    ),
    'kits-call-fixture',
  );
  await fixture(
    `<div style="width:640px;margin:100px auto">${renderToStaticMarkup(createElement(FusionCard, { state: { configured: true, root: '/dedicated/project', runId: 'fixture', status: 'waiting', text: 'Dosya değişikliği için karar bekleniyor.', error: null, events: ['ToolStarted'], question: { id: '1', data: { tur: 'onay', baslik: 'Dosya düzenleme', hedef: 'src/example.ts', diff: '- önceki içerik\n+ önerilen içerik' } } }, busy: false, onReply() {}, onCancel() {} }))}</div>`,
    'kits-fusion-review-fixture',
  );
  await fixture(
    `<div style="display:flex;gap:32px;justify-content:center;align-items:center;height:90vh">${['blue', 'mint', 'orange', 'purple'].map((color) => `<figure><img src="/dots/v3/${color}.png" width="240" height="240"><figcaption style="text-align:center">${color}</figcaption></figure>`).join('')}</div>`,
    'kits-avatars',
  );
  await page.route('**/kits-host-fixture.html', (route) =>
    route.fulfill({
      contentType: 'text/html; charset=utf-8',
      body: `<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;display:flex;height:100vh;font-family:system-ui;background:#fff}nav{width:76px;background:#262322;display:flex;flex-direction:column;gap:12px;padding:18px 6px;box-sizing:border-box}button{background:transparent;color:#ccc;border:0;border-radius:12px;font-size:9px;overflow-wrap:anywhere;min-height:72px;cursor:pointer}button[aria-current]{background:#45403d;color:#22d3ee}button span{display:block;font-size:25px;margin-bottom:6px}iframe{border:0;flex:1;height:100vh}</style></head><body><nav aria-label="Fusion ana menüsü">${fusionNavigation.map((item, index) => `<button ${item.id === 'kits' ? 'aria-current="page"' : ''} data-section="${item.id}"><span>${renderToStaticMarkup(createElement([House, Clock3, Library, Images, Sparkles][index], { size: 24 }))}</span>${item.label}</button>`).join('')}</nav><iframe title="Fusion Kits" src="${base}/?surface=kits" allow="microphone; autoplay"></iframe></body></html>`,
    }),
  );
  await page.goto(`${base}/kits-host-fixture.html`);
  const embedded = page.frameLocator('iframe');
  await embedded.locator('.wordmark').getByText('Fusion Kits').waitFor();
  if (
    (await embedded.locator('html').getAttribute('data-fusion-surface')) !==
    'kits'
  )
    throw new Error('Host modülü işareti eksik.');
  if (process.env.KITS_VISUAL_THEME === 'dark')
    await embedded.locator('html').evaluate((node) => {
      node.dataset.theme = 'dark';
    });
  const menuLabels = await page.locator('nav button').allTextContents();
  if (menuLabels.length !== 5 || !menuLabels[4].includes('Kits'))
    throw new Error('Ana menü sözleşmesi bozuldu.');
  await badge(
    'HOST MENÜ ÖNİZLEMESİ · KITS GERÇEK YEREL MODÜL · FUSION’A GÖMÜLMEDİ',
  );
  await page.screenshot({
    path: join(out, 'kits-host-menu.png'),
    animations: 'disabled',
  });
  report.screenshots.push('kits-host-menu.png');
  report.checks.push(
    'configured-origin-iframe-loads-real-kits-module',
    'approved-host-menu-order',
  );
  if (process.env.KITS_VISUAL_ASSETS === '1')
    report.checks.push(
      await checkAssets(page, base, space.id, document.id, screenshot),
    );
  if (report.pageErrors.length)
    throw new Error(
      `Arayüz JavaScript hataları: ${report.pageErrors.join('; ')}`,
    );
  report.checks.push(
    'labelled-call-and-fusion-review-fixtures',
    'four-current-avatar-assets',
  );
} catch (error) {
  report.error = error.message;
  process.exitCode = 1;
} finally {
  await browser?.close();
  server.kill('SIGTERM');
  await Promise.race([
    new Promise((resolve) => server.once('close', resolve)),
    delay(3000).then(() => server.kill('SIGKILL')),
  ]);
  closeSync(logFd);
  rmSync(temporary, { recursive: true, force: true });
  writeFileSync(
    join(out, 'report.json'),
    JSON.stringify(report, null, 2) + '\n',
  );
  console.log(JSON.stringify(report, null, 2));
}

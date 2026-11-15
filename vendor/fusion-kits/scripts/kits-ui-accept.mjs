import { chromium } from 'playwright';
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
  rmSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { spawn } from 'node:child_process';
import { setTimeout as delay } from 'node:timers/promises';
import process from 'node:process';
import { WorkspaceStore } from '../src/server/workspace.ts';
import { projectRoot } from './kits-start.mjs';
const temp = mkdtempSync(join(tmpdir(), 'kits-ui-accept-'));
const database = join(temp, 'workspace.sqlite');
const workspace = new WorkspaceStore(database, 'acceptance');
const space = workspace.spaces()[0];
workspace.close();
const base = 'http://127.0.0.1:4490';
const child = spawn(
  process.execPath,
  ['--import', 'tsx', 'src/server/index.ts'],
  {
    cwd: projectRoot,
    env: {
      PATH: process.env.PATH,
      HOME: process.env.HOME,
      HOST: '127.0.0.1',
      PORT: '4490',
      DATABASE_PATH: database,
      OWNER_ID: 'acceptance',
      APP_ORIGIN: base,
      WEB_SEARCH_PROVIDER: 'disabled',
    },
    stdio: 'ignore',
  },
);
let browser;
const report = {
  mode: 'real-local-ui-and-api-no-model',
  checks: [],
  error: null,
};
const request = async (path, method = 'GET', body) => {
  const response = await fetch(`${base}/api${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(`Yerel API: ${response.status}`);
  return response.json();
};
const eventually = async (check) => {
  for (let i = 0; i < 80; i++) {
    if (await check()) return;
    await delay(100);
  }
  throw new Error('UI kabul koşulu zamanında gerçekleşmedi.');
};
try {
  await eventually(async () => {
    try {
      return (await fetch(`${base}/api/workspace`)).ok;
    } catch {
      return false;
    }
  });
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  await page.goto(`${base}/#/spaces/${space.id}`);
  await page
    .locator('.library-heading')
    .getByRole('button', { name: 'New page', exact: true })
    .click();
  await page
    .getByRole('textbox', { name: 'Page title', exact: true })
    .fill('Üst sayfa');
  const parent = page.url().match(/\/pages\/([^/]+)/)[1];
  const path = `/spaces/${space.id}/pages/${parent}`;
  await eventually(async () => (await request(path)).title === 'Üst sayfa');
  await page.getByRole('button', { name: 'Page actions', exact: true }).click();
  await page
    .getByRole('menuitem', { name: 'Markdown source', exact: true })
    .click();
  await page
    .getByRole('textbox', { name: 'Page Markdown', exact: true })
    .fill('# Türkçe başlık\n\n- Bir\n- İki');
  await eventually(async () =>
    (await request(path)).content.includes('Türkçe başlık'),
  );
  report.checks.push('create-page-and-markdown-autosave');
  await page.reload();
  await page
    .getByRole('textbox', { name: 'Page title', exact: true })
    .waitFor();
  if (
    (await page
      .getByRole('textbox', { name: 'Page title', exact: true })
      .inputValue()) !== 'Üst sayfa'
  )
    throw new Error('Reload başlığı kaybetti.');
  await page.getByRole('button', { name: 'Page actions', exact: true }).click();
  await page
    .getByRole('menuitem', { name: 'New subpage', exact: true })
    .click();
  await page.waitForURL(
    (url) => url.hash.includes('/pages/') && !url.hash.endsWith(parent),
  );
  await eventually(
    async () =>
      (await page
        .getByRole('textbox', { name: 'Page title', exact: true })
        .inputValue()) === 'Untitled page',
  );
  await page
    .getByRole('textbox', { name: 'Page title', exact: true })
    .fill('Alt sayfa');
  const childId = page.url().match(/\/pages\/([^/]+)/)[1];
  await eventually(
    async () =>
      (await request(`/spaces/${space.id}/pages/${childId}`)).title ===
      'Alt sayfa',
  );
  if (
    (await request(`/spaces/${space.id}/pages/${childId}`)).parentId !== parent
  )
    throw new Error('Alt sayfa üst bağı kayboldu.');
  report.checks.push('reload-and-subpage-parent-persistence');
  await page.goto(`${base}/#/spaces/${space.id}/pages/${parent}`);
  await eventually(
    async () =>
      (await page
        .getByRole('textbox', { name: 'Page title', exact: true })
        .inputValue()) === 'Üst sayfa',
  );
  await page.getByRole('button', { name: 'Page actions', exact: true }).click();
  await page
    .getByRole('menuitem', { name: 'Markdown source', exact: true })
    .click();
  const original = await request(path);
  await page
    .getByRole('textbox', { name: 'Page Markdown', exact: true })
    .fill('# Yerel taslak');
  await request(path, 'PATCH', {
    expectedRevision: original.revision,
    content: '# Uzak içerik',
  });
  await page.locator('.document-save-notice.conflict').waitFor();
  if (
    (await page
      .getByRole('textbox', { name: 'Page Markdown', exact: true })
      .inputValue()) !== '# Yerel taslak'
  )
    throw new Error('Çatışmada yerel taslak kayboldu.');
  if ((await request(path)).content !== '# Uzak içerik')
    throw new Error('Çatışma uzak içeriği ezdi.');
  const downloadEvent = page.waitForEvent('download');
  await page
    .getByRole('button', { name: 'Download draft', exact: true })
    .click();
  const download = await downloadEvent;
  const downloaded = join(temp, 'draft.md');
  await download.saveAs(downloaded);
  if (readFileSync(downloaded, 'utf8') !== '# Yerel taslak')
    throw new Error('İndirilen taslak yanlış.');
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Load latest', exact: true }).click();
  await eventually(
    async () =>
      (await page
        .getByRole('textbox', { name: 'Page Markdown', exact: true })
        .inputValue()) === '# Uzak içerik',
  );
  report.checks.push(
    'real-revision-conflict-preserves-both-drafts',
    'download-draft-and-load-latest',
  );
} catch (error) {
  report.error = error.message;
  process.exitCode = 1;
} finally {
  await browser?.close();
  if (child.exitCode === null)
    await new Promise((resolve) => {
      const timer = setTimeout(() => child.kill('SIGKILL'), 2000);
      child.once('close', () => {
        clearTimeout(timer);
        resolve();
      });
      child.kill('SIGTERM');
    });
  rmSync(temp, { recursive: true, force: true });
  mkdirSync(join(projectRoot, 'handoff/evidence'), { recursive: true });
  writeFileSync(
    join(projectRoot, 'handoff/evidence/ui-accept.json'),
    JSON.stringify(report, null, 2) + '\n',
  );
  console.log(JSON.stringify(report, null, 2));
}

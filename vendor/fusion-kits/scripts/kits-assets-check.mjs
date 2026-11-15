/** Gerçek Python stdio + gerçek App AssetHost + Kits belge/CAS kaydı; sentetik dosya. */
import {
  mkdtempSync,
  mkdirSync,
  rmSync,
  existsSync,
  readFileSync,
  realpathSync,
  writeFileSync,
  copyFileSync,
  chmodSync,
} from 'node:fs';
import { createHash, randomBytes } from 'node:crypto';
import ts from 'typescript';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import process from 'node:process';
import { FusionSession } from '../src/server/fusion/session.ts';
import { processTransport } from '../src/server/fusion/transport.ts';
import { fusionConfig } from '../src/server/fusion/config.ts';

export async function checkAssets(page, base, spaceId, pageId, screenshot) {
  const python = process.env.KITS_FUSION_SMOKE_COMMAND;
  const packaged = process.env.KITS_FUSION_PACKAGED_COMMAND;
  const hostSource = readFileSync(
    resolve(import.meta.dirname, '../../fusion-cli/app/src/kits/assetHost.ts'),
    'utf8',
  );
  const hostModule = ts.transpileModule(hostSource, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ESNext,
    },
  }).outputText;
  if (!python || !existsSync(python))
    throw new Error('Gerçek Fusion Python yolu gerekli.');
  const temporary = mkdtempSync(join(tmpdir(), 'fusion-asset-host-'));
  const root = join(temporary, 'project'),
    home = join(temporary, 'home');
  mkdirSync(root);
  mkdirSync(home);
  const bootstrap = `import asyncio,os
from pathlib import Path
from cryptography.fernet import Fernet
os.environ['FUSION_SECRET_KEY']=Fernet.generate_key().decode()
os.environ['FUSION_NO_NATIVE_HOST']='1'
from fusion_cli.config.paths import user_data_dir
from PIL import Image
gallery=user_data_dir()/'gallery'
gallery.mkdir(parents=True,exist_ok=True)
Image.new('RGBA',(96,64),(40,100,220,180)).save(gallery/'asset-fixture.png')
from fusion_cli.appserver.server import run_stdio
asyncio.run(run_stdio(Path.cwd(),Path(os.environ['FUSION_HOME'])))`;
  let command = python,
    args = ['-c', bootstrap];
  if (packaged) {
    if (!existsSync(packaged) || !process.env.KITS_ASSET_FIXTURE_PNG)
      throw new Error('Paketlenmiş çekirdek ve PNG fixture gerekli.');
    const gallery = join(
      home,
      createHash('sha256').update('asset-smoke').digest('hex'),
      'data/fusion-cli/gallery',
    );
    mkdirSync(gallery, { recursive: true });
    copyFileSync(
      process.env.KITS_ASSET_FIXTURE_PNG,
      join(gallery, 'asset-fixture.png'),
    );
    const quote = (value) => "'" + value.replaceAll("'", "'\\''") + "'";
    command = join(temporary, 'packed-core.sh');
    writeFileSync(
      command,
      `#!/bin/sh\nexport FUSION_SECRET_KEY=${randomBytes(32).toString('base64url')}\nexport FUSION_NO_NATIVE_HOST=1\nexec ${quote(packaged)} app\n`,
    );
    chmodSync(command, 0o700);
    args = [];
  }
  const config = fusionConfig({
    FUSION_COMMAND: command,
    FUSION_ARGS: JSON.stringify(args),
    FUSION_ROOT: root,
    FUSION_HOME: home,
    FUSION_REQUEST_TIMEOUT_MS: '30000',
    FUSION_SHUTDOWN_TIMEOUT_MS: '1500',
  });
  const session = new FusionSession(
    processTransport(config, 'asset-smoke'),
    30000,
  );
  const path = `${base}/fusion-assets-host.html`;
  const modulePath = `${base}/fusion-assets-host-module.js`;
  try {
    const list = await session.request('artefakt.liste', { sinir: 50 });
    if (list.ok !== true || list.items?.length !== 1)
      throw new Error('Gerçek galeri sayfası okunamadı.');
    const id = list.items[0].asset_id;
    await page.exposeFunction('__fusionAssetRpc', (name, data) => {
      if (!['artefakt.liste', 'artefakt.coz', 'artefakt.onizle'].includes(name))
        throw new Error('Beklenmeyen smoke RPC.');
      return session.request(name, data);
    });
    const theme = process.env.KITS_VISUAL_THEME === 'dark' ? 'dark' : 'light';
    await page.route(path, (route) =>
      route.fulfill({
        contentType: 'text/html',
        body: `<html><body style="margin:0"><iframe title="Gerçek Kits dosya köprüsü" style="width:100%;height:100vh;border:0" src="${base}/?surface=kits&theme=${theme}&asset_protocol=1#/spaces/${spaceId}/pages/${pageId}"></iframe></body></html>`,
      }),
    );
    await page.route(modulePath, (route) =>
      route.fulfill({
        contentType: 'application/javascript',
        body: hostModule,
      }),
    );
    await page.goto(path);
    await page.evaluate(
      async ({ base }) => {
        const { AssetHost } = await import(
          `${base}/fusion-assets-host-module.js`
        );
        const frame = globalThis.document.querySelector('iframe');
        globalThis.__assetHost = new AssetHost(
          globalThis.window,
          frame.contentWindow,
          base,
          (name, data) => globalThis.__fusionAssetRpc(name, data),
        );
      },
      { base },
    );
    const frame = page.frameLocator('iframe');
    await frame
      .getByRole('button', { name: "Fusion'dan görsel ekle", exact: true })
      .click();
    await frame
      .getByRole('button', { name: 'asset-fixture.png', exact: true })
      .click();
    const card = frame.locator(`[data-asset-id="${id}"]`);
    await card.scrollIntoViewIfNeeded();
    await card.getByRole('img', { name: 'asset-fixture.png' }).waitFor();
    if (
      !(await card
        .getByRole('img')
        .evaluate((img) => img.complete && img.naturalWidth > 0))
    )
      throw new Error('Gerçek dosya önizlemesi çözülmedi.');
    await frame
      .getByText('Tüm değişiklikler kaydedildi', { exact: true })
      .waitFor();
    const stored = await page.request
      .get(`${base}/api/spaces/${spaceId}/pages/${pageId}`)
      .then((r) => r.json());
    if (
      !stored.content.includes(`fusion-asset:${id}`) ||
      stored.content.includes(temporary) ||
      stored.content.includes(realpathSync(temporary))
    )
      throw new Error('Kimlik/CAS kaydı veya yol gizliliği bozuldu.');
    await screenshot('kits-asset-roundtrip-desktop');
    await page.setViewportSize({ width: 390, height: 844 });
    await card.scrollIntoViewIfNeeded();
    await screenshot('kits-asset-roundtrip-mobile');
    await frame.locator('html').evaluate(() => globalThis.location.reload());
    await frame.locator(`[data-asset-id="${id}"]`).scrollIntoViewIfNeeded();
    await frame.getByRole('img', { name: 'asset-fixture.png' }).waitFor();
    const resolved = await session.request('artefakt.coz', { asset_id: id });
    const file = resolved.asset?.path;
    if (
      typeof file !== 'string' ||
      !resolve(file).startsWith(realpathSync(temporary) + '/')
    )
      throw new Error('Smoke dosyası geçici kökte değil.');
    rmSync(file);
    await frame.locator('html').evaluate(() => globalThis.location.reload());
    await frame.locator(`[data-asset-id="${id}"]`).scrollIntoViewIfNeeded();
    await frame
      .getByText('Dosya artık bulunamıyor; belge kimliği korundu.', {
        exact: true,
      })
      .waitFor();
    await screenshot('kits-asset-missing-mobile');
    return {
      check:
        'real-python-stdio-app-host-gallery-page-id-cas-reload-missing-no-model',
      appHostSourceSha256: createHash('sha256')
        .update(hostSource)
        .digest('hex'),
      native: false,
      packagedCore: Boolean(packaged),
    };
  } finally {
    await page.evaluate(() => globalThis.__assetHost?.close()).catch(() => {});
    await session.close();
    await page.unroute(path).catch(() => {});
    await page.unroute(modulePath).catch(() => {});
    rmSync(temporary, { recursive: true, force: true });
  }
}

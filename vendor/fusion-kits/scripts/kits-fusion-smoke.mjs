import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import process from 'node:process';
import { FusionSession } from '../src/server/fusion/session.ts';
import { processTransport } from '../src/server/fusion/transport.ts';
import { fusionConfig } from '../src/server/fusion/config.ts';
import { projectRoot } from './kits-start.mjs';

// Gerçek çekirdekte yalnız protokol/oturum okunur; model görevi veya kullanıcı verisi yok.
const command = process.env.KITS_FUSION_SMOKE_COMMAND;
if (!command)
  throw new Error('KITS_FUSION_SMOKE_COMMAND mutlak runtime yolu gerekli.');
const temp = mkdtempSync(join(tmpdir(), 'fusion-kits-protocol-'));
const root = join(temp, 'project');
const home = join(temp, 'home');
mkdirSync(root);
mkdirSync(home);
writeFileSync(join(root, 'kanit.txt'), 'Fusion Kits — Türkçe protokol kanıtı');
const config = fusionConfig({
  FUSION_COMMAND: command,
  FUSION_ARGS: process.env.KITS_FUSION_SMOKE_ARGS ?? '["app"]',
  FUSION_ROOT: root,
  FUSION_HOME: home,
  FUSION_REQUEST_TIMEOUT_MS: '30000',
  FUSION_SHUTDOWN_TIMEOUT_MS: '1500',
});
const session = new FusionSession(
  processTransport(config, 'smoke'),
  config.requestTimeoutMs,
);
const report = {
  mode: 'real-fusion-process-isolated-no-model-task',
  checks: [],
  liveModel: false,
  error: null,
};
try {
  const started = await session.request('oturum.baslat', {
    kok: root,
    ev: home,
    sohbet_id: 'kits-smoke',
    mod: 'security',
    kip: 'kod',
    motor: 'agent',
  });
  if (started.ok !== true || started.kok !== root || started.mod !== 'security')
    throw new Error('Gerçek oturum sözleşmesi eşleşmedi.');
  report.checks.push('real-session-start-and-root-security-mode');
  const status = await session.request('oturum.durum', {});
  if (status.ok !== true || status.kok !== root)
    throw new Error('Gerçek durum sözleşmesi eşleşmedi.');
  report.checks.push('real-session-status');
} catch (error) {
  report.error = error.message;
  process.exitCode = 1;
} finally {
  await session.close();
  report.checks.push('process-closed');
  rmSync(temp, { recursive: true, force: true });
  mkdirSync(join(projectRoot, 'handoff/evidence'), { recursive: true });
  writeFileSync(
    join(projectRoot, 'handoff/evidence/real-fusion-smoke.json'),
    JSON.stringify(report, null, 2) + '\n',
  );
  console.log(JSON.stringify(report, null, 2));
}

import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import process from 'node:process';
import { projectRoot } from './kits-start.mjs';
const secret = randomBytes(32).toString('hex');
const base = 'http://127.0.0.1:4491';
const child = spawn(
  process.execPath,
  ['--import', 'tsx', 'src/browser/index.ts'],
  {
    cwd: projectRoot,
    env: {
      PATH: process.env.PATH,
      HOME: process.env.HOME,
      BROWSER_SECRET: secret,
      BROWSER_HOST: '127.0.0.1',
      BROWSER_PORT: '4491',
    },
    stdio: 'ignore',
  },
);
const report = {
  mode: 'real-browser-worker-public-web',
  checks: [],
  error: null,
};
const browse = (url, authorized = true) =>
  fetch(`${base}/browse`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(authorized ? { Authorization: `Bearer ${secret}` } : {}),
    },
    body: JSON.stringify({ url }),
    signal: globalThis.AbortSignal.timeout(45000),
  });
try {
  let ready = false;
  for (let i = 0; i < 100; i++) {
    try {
      ready = (
        await fetch(`${base}/health`, {
          headers: { Authorization: `Bearer ${secret}` },
        })
      ).ok;
    } catch {
      /* Worker henüz hazır olmayabilir. */
    }
    if (ready) break;
    await delay(100);
  }
  if (!ready) throw new Error('Browser worker başlamadı.');
  if (
    (await browse('https://github.com/CopilotKit/OpenDots', false)).status !==
    401
  )
    throw new Error('Yetkisiz okuma reddedilmedi.');
  const privateResponse = await browse('http://127.0.0.1:4491/health');
  if (privateResponse.ok) throw new Error('Özel adres reddedilmedi.');
  report.checks.push('unauthenticated-request-denied', 'private-target-denied');
  const response = await browse('https://github.com/CopilotKit/OpenDots');
  if (!response.ok)
    throw new Error(`Canlı public-page okuma HTTP ${response.status}`);
  const result = await response.json();
  if (!result.text?.includes('OpenDots') || !result.screenshot)
    throw new Error('Kaynak metni veya capture eksik.');
  report.checks.push('real-public-page-text-and-capture');
} catch (error) {
  report.error = error.message;
  process.exitCode = 1;
} finally {
  if (child.exitCode === null)
    await new Promise((resolve) => {
      const timer = setTimeout(() => child.kill('SIGKILL'), 2000);
      child.once('close', () => {
        clearTimeout(timer);
        resolve();
      });
      child.kill('SIGTERM');
    });
  mkdirSync(join(projectRoot, 'handoff/evidence'), { recursive: true });
  writeFileSync(
    join(projectRoot, 'handoff/evidence/browser-smoke.json'),
    JSON.stringify(report, null, 2) + '\n',
  );
  console.log(JSON.stringify(report, null, 2));
}

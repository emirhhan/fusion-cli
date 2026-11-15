import {
  mkdtempSync,
  mkdirSync,
  writeFileSync,
  readFileSync,
  rmSync,
  existsSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import process from 'node:process';
import { performance } from 'node:perf_hooks';
import { FusionSession } from '../src/server/fusion/session.ts';
import { processTransport } from '../src/server/fusion/transport.ts';
import { fusionConfig } from '../src/server/fusion/config.ts';
import { projectRoot } from './kits-start.mjs';

if (existsSync(join(projectRoot, '.env')))
  process.loadEnvFile(join(projectRoot, '.env'));
const configured = fusionConfig(process.env);
if (!configured) throw new Error('Kits Fusion runtime bağlantısı gerekli.');
if (
  new URL(process.env.OPENAI_BASE_URL ?? '').hostname !==
    'integrate.api.nvidia.com' ||
  !process.env.OPENAI_API_KEY
)
  throw new Error(
    'Bu smoke için yapılandırılmış NVIDIA model bağlantısı gerekli.',
  );
const temp = mkdtempSync(join(tmpdir(), 'fusion-kits-model-'));
const root = join(temp, 'project');
const home = join(temp, 'home');
mkdirSync(root);
mkdirSync(home);
const expected = `fusion-kits-${randomUUID()}`;
const input = join(root, 'kanit.txt');
writeFileSync(input, `${expected}\n`);
// Kullanıcının talimatıyla yalnız mevcut NVIDIA anahtarı izole test evine taşınır.
// Bu dizin sonunda kaldırılır; aktif Fusion ayarı ve hesabı kullanılmaz.
writeFileSync(
  join(home, '.env'),
  `NVIDIA_NIM_API_KEY=${process.env.OPENAI_API_KEY}\n`,
  { mode: 0o600 },
);
const config = { ...configured, root, home };
const session = new FusionSession(
  processTransport(config, 'model-smoke'),
  config.requestTimeoutMs,
);
const report = {
  mode: 'real-isolated-fusion-nemotron-read-only',
  passed: false,
  events: [],
  checks: {},
  questionCount: 0,
  elapsedMs: 0,
  error: null,
};
const events = new Set();
session.onEvent((event) => {
  if (typeof event.olay === 'string') events.add(event.olay);
});
session.onQuestion((id) => {
  report.questionCount += 1;
  // Bu test yalnız okur; mutasyon onayı otomatik verilmez.
  session.reply(id, { secim: 'deny' });
});
const start = performance.now();
let stage = 'session-start';
try {
  const started = await session.request('oturum.baslat', {
    kok: root,
    ev: home,
    sohbet_id: 'kits-model-smoke',
    mod: 'security',
    kip: 'sohbet',
    motor: 'agent',
  });
  if (started.ok !== true) throw new Error('Oturum açılamadı.');
  stage = 'read-only-model-turn';
  const result = await session.request('tur.calistir', {
    gorev:
      'Çalışma dizinindeki kanit.txt dosyasını yalnız oku. İçindeki kodu cevabında aynen yaz. Hiçbir dosyayı değiştirme, komut çalıştırma veya ağ aracı kullanma.',
    sesli: {},
  });
  stage = 'result-verification';
  report.checks = {
    resultOk: result.ok === true,
    hasText: typeof result.metin === 'string',
    expectedMatched:
      typeof result.metin === 'string' && result.metin.includes(expected),
    toolStarted: events.has('ToolStarted'),
    fileUnchanged: readFileSync(input, 'utf8') === `${expected}\n`,
  };
  if (
    result.ok !== true ||
    typeof result.metin !== 'string' ||
    !result.metin.includes(expected) ||
    !events.has('ToolStarted') ||
    readFileSync(input, 'utf8') !== `${expected}\n`
  )
    throw new Error('Dosya okuma kanıtı eşleşmedi.');
  report.passed = true;
} catch {
  report.error = `${stage} başarısız; sır ve sağlayıcı yanıtı kaydedilmedi.`;
  process.exitCode = 1;
} finally {
  await session.close();
  rmSync(temp, { recursive: true, force: true });
  report.events = [...events];
  report.elapsedMs = Math.round(performance.now() - start);
  mkdirSync(join(projectRoot, 'handoff/evidence'), { recursive: true });
  writeFileSync(
    join(projectRoot, 'handoff/evidence/real-fusion-model-smoke.json'),
    JSON.stringify(report, null, 2) + '\n',
  );
  console.log(JSON.stringify(report, null, 2));
}

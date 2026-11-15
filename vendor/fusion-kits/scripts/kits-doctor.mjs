import { parseEnv } from 'node:util';
import { pathToFileURL } from 'node:url';
import { existsSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import process from 'node:process';
import { assertRuntime, projectRoot } from './kits-start.mjs';
const groups = {
  model: ['OPENAI_API_KEY', 'OPENAI_MODEL'],
  conversations: ['INTELLIGENCE_API_KEY'],
  voice: ['VOICE_API_KEY', 'VOICE_MODEL'],
  slack: ['SLACK_CHANNEL_NAME', 'SLACK_TEAM_ID', 'SLACK_USER_IDS'],
  computer: [
    'COMPUTER_SUPERVISOR_URL',
    'COMPUTER_SUPERVISOR_TOKEN',
    'COMPUTER_TOKEN',
  ],
  fusion: ['FUSION_COMMAND', 'FUSION_ROOT', 'FUSION_HOME'],
};
export function configurationPresence(raw) {
  const local = parseEnv(raw);
  return Object.fromEntries(
    Object.entries(groups).map(([name, keys]) => [
      name,
      {
        configured: keys.every((key) => !!local[key]?.trim()),
        missing: keys.filter((key) => !local[key]?.trim()),
      },
    ]),
  );
}
export function dockerEngineAvailable(result) {
  return (
    result.status === 0 &&
    /^\d+\.\d+(?:\.\d+)?(?:[-+][\w.-]+)?$/.test(
      String(result.stdout ?? '').trim(),
    )
  );
}
if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  assertRuntime();
  const localEnv = join(projectRoot, '.env');
  const configured = configurationPresence(
    existsSync(localEnv) ? readFileSync(localEnv, 'utf8') : '',
  );
  const docker = spawnSync(
    'docker',
    ['info', '--format', '{{.ServerVersion}}'],
    {
      timeout: 5000,
      stdio: 'pipe',
    },
  );
  const report = {
    node: process.versions.node,
    platform: process.platform,
    groups: configured,
    dockerAvailable: dockerEngineAvailable(docker),
    liveSuccess: false,
    note: 'Yalnız yapılandırma varlığıdır; canlı başarı kanıtı değildir. Sır değerleri kaydedilmez.',
  };
  mkdirSync(join(projectRoot, 'handoff/evidence'), { recursive: true });
  writeFileSync(
    join(projectRoot, 'handoff/evidence/doctor.json'),
    JSON.stringify(report, null, 2) + '\n',
  );
  console.log(JSON.stringify(report, null, 2));
}

import { mkdirSync, openSync, closeSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import process from 'node:process';
import { assertRuntime, projectRoot } from './kits-start.mjs';

assertRuntime();
const evidence = resolve(projectRoot, 'handoff/evidence');
mkdirSync(evidence, { recursive: true });
const results = [];
for (const command of ['check-format', 'lint', 'typecheck', 'test', 'build']) {
  const log = resolve(evidence, `final-${command}.log`);
  const fd = openSync(log, 'w');
  const result = spawnSync(
    process.execPath,
    [process.env.npm_execpath, 'run', command],
    {
      cwd: projectRoot,
      env: process.env,
      stdio: ['ignore', fd, fd],
    },
  );
  closeSync(fd);
  results.push({
    command,
    code: result.status,
    error: result.error?.message ?? null,
    log: `handoff/evidence/final-${command}.log`,
  });
  console.log(`${command}: ${result.status === 0 ? 'GEÇTİ' : 'BAŞARISIZ'}`);
}
writeFileSync(
  resolve(evidence, 'checks.json'),
  JSON.stringify({ node: process.versions.node, results }, null, 2) + '\n',
);
if (results.some((result) => result.code !== 0)) process.exitCode = 1;

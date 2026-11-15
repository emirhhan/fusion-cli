import { mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import process from 'node:process';
import { parallelSources } from '../src/server/parallel.ts';
import { projectRoot } from './kits-start.mjs';
const report = {
  provider: 'parallel-anonymous',
  live: true,
  modelUsed: false,
  sourceCount: 0,
  nonemptyEvidence: false,
  error: null,
};
try {
  const sources = await parallelSources(
    {
      objective:
        'Read the public repository overview and identify the project name.',
      urls: ['https://github.com/CopilotKit/OpenDots'],
      sessionId: 'fusion-kits-public-smoke',
    },
    { webSearchProvider: 'parallel' },
    globalThis.AbortSignal.timeout(20000),
  );
  report.sourceCount = sources.length;
  report.nonemptyEvidence = sources.some(
    (source) => source.text.trim().length > 0,
  );
  if (!report.nonemptyEvidence) throw new Error('Canlı araştırma kanıtı boş.');
} catch (error) {
  report.error = error.message;
  process.exitCode = 1;
}
mkdirSync(join(projectRoot, 'handoff/evidence'), { recursive: true });
writeFileSync(
  join(projectRoot, 'handoff/evidence/public-web-smoke.json'),
  JSON.stringify(report, null, 2) + '\n',
);
console.log(JSON.stringify(report, null, 2));

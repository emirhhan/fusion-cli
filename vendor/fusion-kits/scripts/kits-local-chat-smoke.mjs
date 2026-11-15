// Yerel sohbet kabulü: dış sohbet servisi olmadan gerçek modelle bir tur, ardından
// sunucu yeniden başlatılır ve geçmişin diskten geri geldiği doğrulanır.
import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import process from 'node:process';
import { HttpAgent } from '@ag-ui/client';

const port = Number(process.env.KITS_SMOKE_PORT ?? 47412);
const base = `http://127.0.0.1:${port}`;
const database = join(
  mkdtempSync(join(tmpdir(), 'kits-local-chat-')),
  'kits.sqlite',
);
const code = `KITS-${Math.floor(1000 + Math.random() * 9000)}`;

function start() {
  const child = spawn(
    process.execPath,
    ['--env-file-if-exists=.env', 'dist/server/server/index.js'],
    {
      env: {
        ...process.env,
        HOST: '127.0.0.1',
        PORT: String(port),
        DATABASE_PATH: database,
        INTELLIGENCE_API_KEY: '',
      },
      stdio: ['ignore', 'ignore', 'inherit'],
    },
  );
  return child;
}
async function ready() {
  for (let attempt = 0; attempt < 80; attempt++) {
    try {
      if ((await fetch(`${base}/api/workspace`)).ok) return;
    } catch {
      /* henüz dinlemiyor */
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error('Kits sunucusu hazır olmadı.');
}
async function stop(child) {
  child.kill('SIGTERM');
  await new Promise((resolve) => child.once('exit', resolve));
}
const json = async (path, init) => {
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
  });
  return { status: response.status, body: await response.json() };
};
const assistantText = (messages) =>
  messages
    .filter((message) => message.role === 'assistant')
    .map((message) =>
      typeof message.content === 'string' ? message.content : '',
    )
    .join('\n');

const report = { passed: false, steps: {} };
let server = start();
try {
  await ready();
  const workspace = (await json('/api/workspace')).body;
  report.steps.setupMissing = workspace.setup.missing;
  if (workspace.setup.missing.length)
    throw new Error(`Kurulum eksik: ${workspace.setup.missing.join(', ')}`);
  const dot = workspace.dots[0];
  const created = await json('/api/conversations', {
    method: 'POST',
    body: JSON.stringify({ dotId: dot.id, title: 'Yerel sohbet kabulü' }),
  });
  report.steps.conversationStatus = created.status;
  const threadId = created.body.id;
  const agent = new HttpAgent({
    url: `${base}/api/copilotkit/agent/${encodeURIComponent(dot.id)}/run`,
    agentId: dot.id,
  });
  agent.threadId = threadId;
  agent.addMessage({
    id: randomUUID(),
    role: 'user',
    content: `Hiçbir araç kullanma. Yalnızca şu kodu aynen yaz: ${code}`,
  });
  const startedAt = Date.now();
  const result = await agent.runAgent();
  report.steps.turnMs = Date.now() - startedAt;
  report.steps.replyHasCode = assistantText(result.newMessages).includes(code);

  await stop(server);
  server = start();
  await ready();
  const threads = (await json('/api/copilotkit/threads')).body;
  const listed = (threads.threads ?? threads).find?.(
    (thread) => thread.id === threadId,
  );
  report.steps.threadListedAfterRestart = Boolean(listed);
  report.steps.threadName = listed?.name ?? null;
  const reconnect = new HttpAgent({
    url: `${base}/api/copilotkit/agent/${encodeURIComponent(dot.id)}/connect`,
    agentId: dot.id,
  });
  reconnect.threadId = threadId;
  await reconnect.runAgent();
  report.steps.historyAfterRestartHasCode = assistantText(
    reconnect.messages,
  ).includes(code);
  report.steps.historyRoles = reconnect.messages.map((message) => message.role);
  report.passed =
    report.steps.replyHasCode &&
    report.steps.threadListedAfterRestart &&
    report.steps.historyAfterRestartHasCode;
} catch (error) {
  report.error = error instanceof Error ? error.message : String(error);
} finally {
  await stop(server).catch(() => undefined);
}
writeFileSync(
  'handoff/evidence/local-chat-smoke.json',
  `${JSON.stringify(report, null, 2)}\n`,
);
console.log(JSON.stringify(report, null, 2));
process.exitCode = report.passed ? 0 : 1;

import { readFileSync, existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { parseEnv } from 'node:util';
import { join } from 'node:path';
import process from 'node:process';
import { projectRoot } from './kits-start.mjs';
const path = join(projectRoot, '.env');
const local = existsSync(path) ? parseEnv(readFileSync(path, 'utf8')) : {};
const report = {
  mode: 'actual-configured-model-stream-and-tool-call',
  status: 'blocked',
  checks: [],
  error: null,
};
try {
  if (!local.OPENAI_API_KEY?.trim() || !local.OPENAI_MODEL?.trim()) {
    report.error = 'Paketin yerel model ayarları eksik.';
    process.exitCode = 2;
  } else {
    const base = new URL(local.OPENAI_BASE_URL || 'https://api.openai.com/v1');
    if (
      !['https:', 'http:'].includes(base.protocol) ||
      base.username ||
      base.password ||
      base.search ||
      base.hash
    )
      throw new Error('Geçersiz model endpoint.');
    const response = await fetch(
      `${base.toString().replace(/\/$/, '')}/chat/completions`,
      {
        method: 'POST',
        redirect: 'error',
        headers: {
          Authorization: `Bearer ${local.OPENAI_API_KEY}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: local.OPENAI_MODEL,
          messages: [
            {
              role: 'user',
              content:
                'Acceptance test: call kits_probe once with ok:true. Do not perform any external actions.',
            },
          ],
          tools: [
            {
              type: 'function',
              function: {
                name: 'kits_probe',
                description: 'Returns acceptance probe result only.',
                parameters: {
                  type: 'object',
                  properties: { ok: { type: 'boolean' } },
                  required: ['ok'],
                  additionalProperties: false,
                },
              },
            },
          ],
          stream: true,
          max_completion_tokens: 500,
        }),
        signal: globalThis.AbortSignal.timeout(60000),
      },
    );
    if (!response.ok) throw new Error(`Model HTTP ${response.status}`);
    if (!response.headers.get('content-type')?.includes('text/event-stream'))
      throw new Error('Model SSE döndürmedi.');
    const reader = response.body.getReader();
    const chunks = [];
    let total = 0;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        total += value.byteLength;
        if (total > 262144) throw new Error('Model probe yanıt sınırı aşıldı.');
        chunks.push(value);
      }
    } finally {
      await reader.cancel();
    }
    const calls = new Map();
    for (const line of Buffer.concat(chunks).toString('utf8').split(/\r?\n/)) {
      if (!line.startsWith('data:')) continue;
      const raw = line.slice(5).trim();
      if (!raw || raw === '[DONE]') continue;
      const event = JSON.parse(raw);
      if (event.error) throw new Error('Model stream hata bildirdi.');
      for (const call of event.choices?.[0]?.delta?.tool_calls ?? []) {
        const existing = calls.get(call.index) ?? { name: '', args: '' };
        existing.name += call.function?.name ?? '';
        existing.args += call.function?.arguments ?? '';
        calls.set(call.index, existing);
      }
    }
    if (
      ![...calls.values()].some(
        (call) =>
          call.name === 'kits_probe' && JSON.parse(call.args).ok === true,
      )
    )
      throw new Error('Model geçerli probe araç çağrısı üretmedi.');
    report.status = 'passed';
    report.checks.push(
      'real-provider-sse-stream',
      'real-provider-tool-call-and-json-arguments',
    );
  }
} catch (error) {
  report.status = 'failed';
  report.error =
    error instanceof SyntaxError
      ? 'Model stream veya araç argümanları geçerli JSON değil.'
      : error.message;
  process.exitCode = 1;
}
mkdirSync(join(projectRoot, 'handoff/evidence'), { recursive: true });
writeFileSync(
  join(projectRoot, 'handoff/evidence/model-smoke.json'),
  JSON.stringify(report, null, 2) + '\n',
);
console.log(JSON.stringify(report, null, 2));

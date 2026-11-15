import { randomUUID } from 'node:crypto';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { z } from 'zod';

export type WebSearchProvider = 'parallel' | 'browser' | 'disabled';
export interface WebConfig {
  webSearchProvider?: WebSearchProvider;
  parallelApiKey?: string;
}
export function webSearchProvider(value?: string): WebSearchProvider {
  if (!value) return 'parallel';
  if (value === 'parallel' || value === 'browser' || value === 'disabled')
    return value;
  throw new Error(
    'WEB_SEARCH_PROVIDER parallel, browser veya disabled olmalı.',
  );
}
const source = z.object({
  url: z
    .string()
    .url()
    .refine((value) => {
      const url = new URL(value);
      return (
        ['http:', 'https:'].includes(url.protocol) &&
        !url.username &&
        !url.password
      );
    }),
  title: z.string().nullable().optional(),
  excerpts: z.array(z.string()).default([]),
});
export interface WebSource {
  title: string;
  url: string;
  text: string;
}
export function sourcesFromResult(
  result: unknown,
  warn: (message: string) => void = () => {},
): WebSource[] {
  const envelope = z
    .object({
      isError: z.boolean().optional(),
      structuredContent: z.unknown().optional(),
      content: z
        .array(z.object({ type: z.string(), text: z.string().optional() }))
        .optional(),
    })
    .parse(result);
  if (envelope.isError)
    throw new Error(
      'Parallel web isteğini tamamlayamadı. Daha sonra yeniden dene veya sağlayıcı kotasını kontrol et.',
    );
  let data = envelope.structuredContent;
  if (!data) {
    const text = envelope.content?.find((item) => item.type === 'text')?.text;
    try {
      data = JSON.parse(text ?? '');
    } catch {
      throw new Error('Parallel geçersiz bir yanıt döndürdü.');
    }
  }
  const parsed = z
    .object({
      results: z.array(z.unknown()),
      errors: z.array(z.unknown()).optional(),
      warnings: z.array(z.unknown()).nullable().optional(),
    })
    .parse(data);
  if (parsed.errors?.length)
    warn(
      `Sağlayıcı ${parsed.errors.length} kaynak çıkarma hatası bildirdi; kapsam eksik.`,
    );
  if (parsed.warnings?.length)
    warn('Sağlayıcı uyarılar döndürdü; bazı kaynak kanıtları eksik olabilir.');
  let discarded = 0;
  const seen = new Set<string>();
  const sources = parsed.results
    .flatMap((item) => {
      const parsedSource = source.safeParse(item);
      if (!parsedSource.success) {
        discarded++;
        return [];
      }
      const value = parsedSource.data;
      if (seen.has(value.url)) return [];
      if (!value.excerpts.some((text) => text.trim())) {
        discarded++;
        return [];
      }
      seen.add(value.url);
      return [
        {
          title: value.title || value.url,
          url: value.url,
          text: value.excerpts.join('\n').slice(0, 6000),
        },
      ];
    })
    .slice(0, 5);
  if (discarded)
    warn(`Hatalı veya boş ${discarded} kaynak sonucu atlandı; kapsam eksik.`);
  return sources;
}
export async function parallelSources(
  request: {
    objective: string;
    urls?: string[];
    sessionId?: string;
    searchQueries?: string[];
    onWarning?: (message: string) => void;
  },
  config: WebConfig,
  signal: AbortSignal,
): Promise<WebSource[]> {
  signal.throwIfAborted();
  if ((config.webSearchProvider ?? 'parallel') !== 'parallel')
    throw new Error('Parallel web araştırması kapalı.');
  const client = new Client({ name: 'opendots', version: '0.1.0' });
  const boundedSignal = AbortSignal.any([signal, AbortSignal.timeout(60_000)]);
  const transport = new StreamableHTTPClientTransport(
    new URL('https://search.parallel.ai/mcp'),
    {
      requestInit: config.parallelApiKey
        ? { headers: { Authorization: `Bearer ${config.parallelApiKey}` } }
        : undefined,
      fetch: (url, init) =>
        fetch(url, {
          ...init,
          signal: AbortSignal.any([
            boundedSignal,
            ...(init?.signal ? [init.signal] : []),
          ]),
        }),
    },
  );
  const session_id = request.sessionId ?? randomUUID();
  // Send only the requested research objective and URLs, never memories or the full transcript.
  const objective = request.objective;
  const search_queries = request.searchQueries ?? [objective];
  const warn = request.onWarning ?? (() => {});
  try {
    await client.connect(transport);
    let urls = request.urls;
    if (!urls?.length) {
      const found = sourcesFromResult(
        await client.callTool(
          {
            name: 'web_search',
            arguments: { objective, search_queries, session_id },
          },
          undefined,
          { signal: boundedSignal },
        ),
        warn,
      );
      urls = found.map((page) => page.url);
      if (!urls.length)
        throw new Error(
          'Parallel kullanılabilir kaynak bulamadı. Daha belirli bir araştırma isteği dene.',
        );
    }
    for (const url of urls) source.shape.url.parse(url);
    const pages = sourcesFromResult(
      await client.callTool(
        {
          name: 'web_fetch',
          arguments: {
            urls: urls.slice(0, 5),
            objective:
              objective.length <= 200
                ? objective
                : 'Extract source evidence relevant to the supplied research queries.',
            search_queries,
            session_id,
          },
        },
        undefined,
        { signal: boundedSignal },
      ),
      warn,
    );
    if (urls.length > 5) warn('Yalnızca ilk beş adres okundu; kapsam sınırlı.');
    if (pages.length < Math.min(urls.length, 5))
      warn('İstenen bazı kaynaklar okunamadı; kapsam eksik.');
    boundedSignal.throwIfAborted();
    if (!pages.length)
      throw new Error('Parallel kullanılabilir kaynak kanıtı çıkaramadı.');
    return pages;
  } finally {
    await client.close().catch(() => {});
  }
}

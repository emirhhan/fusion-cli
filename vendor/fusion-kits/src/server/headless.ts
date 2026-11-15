import { IntelligenceAgent } from '@copilotkit/core';
import { HttpAgent } from '@ag-ui/client';
import type { Message } from '@ag-ui/core';
import { randomUUID } from 'node:crypto';
import { z } from 'zod';
import {
  voiceReceiptMessagePrefix,
  voiceUtteranceMessagePrefix,
} from '../shared/voice-receipt.js';

export function currentTurnText(messages: Message[], error?: Error): string {
  if (error) throw error;
  const content = messages
    .filter((message) => message.role === 'assistant')
    .at(-1)?.content;
  if (typeof content !== 'string' || !content.trim())
    throw new Error('Bu işlem turu asistan yanıtı döndürmedi.');
  return content;
}

const runtimeInfoSchema = z.discriminatedUnion('mode', [
  z.object({
    mode: z.literal('intelligence'),
    intelligence: z.object({ wsUrl: z.url() }),
    agents: z.record(z.string(), z.unknown()),
  }),
  // Yerel kip: sohbet geçmişi çağıran taraftan gelir, koşu SSE ile akar.
  z.object({
    mode: z.literal('sse'),
    agents: z.record(z.string(), z.unknown()),
  }),
]);

export async function runThreadTurn(
  runtimeUrl: string,
  headers: Record<string, string>,
  dotId: string,
  threadId: string,
  prompt: string,
  signal: AbortSignal,
  metadata?: Record<string, unknown>,
  history: Message[] = [],
  progress?: (text: string) => void,
  runId?: string,
): Promise<string> {
  signal.throwIfAborted();
  const response = await fetch(`${runtimeUrl}/info`, { headers, signal });
  if (!response.ok)
    throw new Error(
      `Intelligence çalışma ortamı HTTP ${response.status} döndürdü.`,
    );
  const info = runtimeInfoSchema.parse(await response.json());
  if (!Object.hasOwn(info.agents, dotId))
    throw new Error('Seçilen Kit çalışma ortamında kullanılamıyor.');
  // Core's runtime discovery is browser-only. Use the SDK's Node-compatible
  // Intelligence agent for voice compute and scheduled server turns.
  const agent =
    info.mode === 'intelligence'
      ? new IntelligenceAgent({
          url: info.intelligence.wsUrl,
          runtimeUrl,
          agentId: dotId,
          headers,
          fetch: (input, init) =>
            fetch(input, {
              ...init,
              signal: init?.signal
                ? AbortSignal.any([signal, init.signal])
                : signal,
            }),
        })
      : new HttpAgent({
          url: `${runtimeUrl}/agent/${encodeURIComponent(dotId)}/run`,
          agentId: dotId,
          headers,
          initialMessages: history,
        });
  agent.threadId = threadId;
  let runError: Error | undefined;
  const subscription = agent.subscribe({
    onRunErrorEvent: ({ event }) => {
      runError = new Error(event.message);
    },
    // Kesintide devam notu için: hangi adımların başladığı kalıcı kayda düşer.
    onToolCallStartEvent: ({ event }) => {
      // İptal/lease kaybı zaten abortRun ile durdurulur; olay akışını bozma.
      try {
        progress?.(`Adım: ${event.toolCallName}`);
      } catch {
        stop();
      }
    },
  });
  const stop = () => agent.abortRun();
  signal.addEventListener('abort', stop, { once: true });
  try {
    signal.throwIfAborted();
    agent.addMessage({
      id: `${metadata?.opendotsSource === 'voice_receipt' ? voiceReceiptMessagePrefix : metadata?.opendotsSource === 'voice' ? voiceUtteranceMessagePrefix : ''}${randomUUID()}`,
      role: 'user',
      content: prompt,
      ...(metadata ? { metadata } : {}),
    });
    const result = await agent.runAgent(runId ? { runId } : undefined);
    signal.throwIfAborted();
    return currentTurnText(result.newMessages, runError);
  } finally {
    signal.removeEventListener('abort', stop);
    subscription.unsubscribe();
    await agent.detachActiveRun();
  }
}

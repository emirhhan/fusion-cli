import { readinessNotice } from './readiness.js';
import { createShutdown } from './shutdown.js';
import { assertScheduledExecution } from './scheduled-delivery.js';
import { kitsHostOrigins } from './kits-host.js';
import {
  clearKitsState,
  kitsStateFile,
  writeKitsState,
} from './kits-state-file.js';
import { fusionConfig } from './fusion/config.js';
import { startFusionGateway, type FusionGateway } from './fusion/gateway.js';
import { webSearchProvider } from './parallel.js';
import { reportChannelFailure, safeFailure } from './slack-channel.js';
import { serve } from '@hono/node-server';
import { serveStatic } from '@hono/node-server/serve-static';
import { Store } from './store.js';
import { Runner } from './runner.js';
import { createApp } from './app.js';
import { WorkspaceStore } from './workspace.js';
import { Platform } from './platform.js';
import type { PlatformConfig } from './platform-config.js';
import type { KitHostDependencies } from './kit-host.js';
import {
  startLocalComputer,
  type LocalComputerHandle,
} from './local-computer/start.js';
/** Kits'in Fusion geçidinden istediği varsayılan kademe. */
export const DEFAULT_GATEWAY_MODEL = 'medium';
export async function startKits(
  hostDependencies?: KitHostDependencies,
): Promise<{ close(): Promise<void> }> {
  const host = process.env.HOST ?? '127.0.0.1';
  const port = Number(process.env.PORT ?? 4410);
  const ownerToken = process.env.OWNER_TOKEN;
  if (
    !['127.0.0.1', '::1', 'localhost'].includes(host) &&
    (!ownerToken || ownerToken.length < 24)
  )
    throw new Error(
      'Dış bağlantı için en az 24 karakterlik bir OWNER_TOKEN gerekir.',
    );
  const database = process.env.DATABASE_PATH ?? 'data/fusion-kits.sqlite';
  const store = new Store(database);
  let workspace: WorkspaceStore | undefined;
  let platform: Platform | undefined;
  let gateway: FusionGateway | undefined;
  let localComputer: LocalComputerHandle | undefined;
  try {
    workspace = new WorkspaceStore(
      database,
      process.env.OWNER_ID ?? 'fusion-kits-owner',
    );
    gateway = await modelGateway();
    localComputer = await startLocalComputer(process.env, database);
    const config = {
      ...runtimeConfig(database, host, port, ownerToken, gateway),
      ...localComputer?.config,
    };
    platform = new Platform(store, workspace, config, hostDependencies);
    const { runner, researchConfig } = createRunner(
      store,
      workspace,
      platform,
      config,
    );
    const app = createServerApp(
      store,
      runner,
      platform,
      config,
      researchConfig,
      ownerToken,
    );
    const readyPlatform = platform;
    const server = serve({ fetch: app.fetch, hostname: host, port }, (info) => {
      console.log(`Fusion Kits listening on http://${host}:${info.port}`);
      const notice = readinessNotice(process.env, info.port, process.pid);
      if (notice) console.log(notice);
      // Fusion çekirdeği (CLI aracı/masaüstü RPC'si) Kits'i bu dosyadan bulur (P-063).
      const stateFile = kitsStateFile(process.env);
      if (stateFile)
        try {
          writeKitsState(stateFile, `http://${host}:${info.port}`, process.pid);
        } catch (error) {
          console.warn(
            `Kits durum dosyası yazılamadı (Fusion araçları Kits'i bulamayabilir): ${
              error instanceof Error ? error.message : String(error)
            }`,
          );
        }
      runner.start();
      void readyPlatform
        .start()
        .catch((error) =>
          reportChannelFailure(
            'Slack Channels activation failed; check setup status',
            [safeFailure(error)],
          ),
        );
    });
    await new Promise<void>((resolve, reject) => {
      const failed = (error: Error) => {
        server.removeListener('listening', ready);
        reject(error);
      };
      const ready = () => {
        server.removeListener('error', failed);
        resolve();
      };
      server.once('error', failed);
      server.once('listening', ready);
    });
    return ownedClose(
      store,
      workspace,
      platform,
      runner,
      server,
      gateway,
      localComputer,
    );
  } catch (error) {
    try {
      await platform?.stop();
      await gateway?.close();
      await localComputer?.close();
    } finally {
      platform?.localThreads?.close();
      workspace?.close();
      store.close();
    }
    throw error;
  }
}

/**
 * Fusion bağlıysa model çağrıları Fusion geçidinden geçer (429 bekleme, yedek model,
 * hesap havuzu, sağlık). KITS_MODEL_GATEWAY=0 ile kapatılır. Açılamazsa Kits doğrudan
 * sağlayıcıyla çalışmaya devam eder ve bunu açıkça bildirir.
 */
async function modelGateway(): Promise<FusionGateway | undefined> {
  const fusion = fusionConfig(process.env);
  if (!fusion || process.env.KITS_MODEL_GATEWAY === '0') return;
  try {
    const gateway = await startFusionGateway(fusion);
    console.log(`Kits model çağrıları Fusion geçidinden: ${gateway.baseUrl}`);
    return gateway;
  } catch (error) {
    console.warn(
      `Fusion geçidi açılamadı, model doğrudan sağlayıcıya bağlanıyor (Fusion korumaları devre dışı): ${
        error instanceof Error ? error.message : String(error)
      }`,
    );
    return;
  }
}

function ownedClose(
  store: Store,
  workspace: WorkspaceStore,
  platform: Platform,
  runner: Runner,
  server: ReturnType<typeof serve>,
  gateway?: FusionGateway,
  localComputer?: LocalComputerHandle,
) {
  let failed = false;
  const close = createShutdown({
    stopRunner: () => runner.stop(),
    stopPlatform: () => platform.stop(),
    closeServer: async () => {
      await new Promise<void>((resolve, reject) =>
        server.close((error) => (error ? reject(error) : resolve())),
      );
      await gateway?.close();
      await localComputer?.close();
      const stateFile = kitsStateFile(process.env);
      if (stateFile) clearKitsState(stateFile, process.pid);
    },
    exit: (code) => {
      failed = code !== 0;
    },
    report: (operation, error) =>
      reportChannelFailure(operation, [safeFailure(error)]),
  });
  let pending: Promise<void> | undefined;
  return {
    close: () =>
      (pending ??= (async () => {
        try {
          await close();
        } finally {
          platform.localThreads?.close();
          store.close();
          workspace.close();
        }
        if (failed) throw new Error('Kits kapanışı tamamlanamadı.');
      })()),
  };
}

function createRunner(
  store: Store,
  workspace: WorkspaceStore,
  platform: Platform,
  config: PlatformConfig,
) {
  const researchConfig = {
    mode: 'live' as const,
    apiKey: config.apiKey,
    model: config.model,
    baseUrl: config.baseUrl,
    webSearchProvider: config.webSearchProvider,
    parallelApiKey: config.parallelApiKey,
    browserUrl: config.browserUrl,
    browserSecret: config.browserSecret,
  };
  const runner = new Runner(
    store,
    researchConfig,
    async (claim, _memories, signal, progress) => {
      const threadId = workspace.taskThread(claim.id);
      if (!threadId)
        throw new Error(
          'Bu eski görevin bir Intelligence sohbeti yok. Bir sohbetten yeni zamanlanmış görev oluştur.',
        );
      assertScheduledExecution(store, workspace, platform.fusion, claim);
      progress('Bu görev kendi Intelligence sohbetinde çalıştırılıyor.');
      const text = await platform.runTaskTurn(
        claim,
        resumablePrompt(claim.prompt, store.resumeNote(claim)),
        signal,
        progress,
      );
      return { text, sources: [], sample: false };
    },
    (claim) => {
      const threadId = workspace.taskThread(claim.id) ?? '';
      return (
        platform.fusion.busy(threadId) || platform.fusion.waiting(threadId)
      );
    },
  );
  return { runner, researchConfig };
}
function createServerApp(
  store: Store,
  runner: Runner,
  platform: Platform,
  config: PlatformConfig,
  researchConfig: ReturnType<typeof createRunner>['researchConfig'],
  ownerToken?: string,
) {
  const wsOrigin = new URL(
    config.intelligenceWsUrl ?? 'wss://realtime.intelligence.copilotkit.ai',
  ).origin;
  const allowedParentOrigins = kitsHostOrigins(process.env.KITS_HOST_ORIGINS);
  const frameAncestors = allowedParentOrigins.join(' ') || "'none'";
  const app = createApp({
    store,
    runner,
    config: researchConfig,
    ownerToken,
    origin:
      process.env.APP_ORIGIN ??
      (process.env.NODE_ENV === 'development'
        ? 'http://127.0.0.1:4413'
        : undefined),
    platform,
  });
  app.use('*', async (c, next) => {
    c.header('X-Content-Type-Options', 'nosniff');
    c.header('Referrer-Policy', 'no-referrer');
    c.header(
      'Content-Security-Policy',
      `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ${wsOrigin}; media-src 'self' blob:; frame-ancestors ${frameAncestors}; base-uri 'self'; form-action 'self'`,
    );
    await next();
  });
  app.get('/api/host-bridge-policy', (c) => c.json({ allowedParentOrigins }));
  app.get('/api/*', (c) => c.json({ error: 'Bulunamadı.' }, 404));
  app.use('/*', serveStatic({ root: './dist/client' }));
  app.get('*', serveStatic({ path: './dist/client/index.html' }));
  return app;
}

function runtimeConfig(
  database: string,
  host: string,
  port: number,
  ownerToken?: string,
  gateway?: FusionGateway,
): PlatformConfig {
  return {
    fusion: fusionConfig(process.env),
    intelligenceKey: process.env.INTELLIGENCE_API_KEY,
    intelligenceApiUrl: process.env.INTELLIGENCE_API_URL || undefined,
    intelligenceWsUrl: process.env.INTELLIGENCE_WS_URL || undefined,
    // Intelligence anahtarı yoksa sohbetler aynı klasördeki yerel dosyada tutulur.
    localThreadsPath: process.env.INTELLIGENCE_API_KEY
      ? undefined
      : database === ':memory:'
        ? ':memory:'
        : database.replace(/(\.sqlite)?$/, '-threads.sqlite'),
    // Geçit yerel ve anahtarsızdır; sağlayıcı anahtarları Fusion'ın kendi deposunda kalır.
    apiKey: gateway ? 'fusion-local' : process.env.OPENAI_API_KEY,
    // `auto` kullanıcının Fusion ana modelidir; o çoğu zaman bir web oturumu
    // (ChatGPT/Gemini web) ve insan doğrulaması (CAPTCHA) isteyebilir. Kits
    // arka planda başında kimse yokken de çalıştığı için varsayılan, anahtarlı
    // API kademesidir (ölçüldü 9 Eki 2026: `auto` 41 sn'de boş, `medium` 8 sn'de cevap).
    model: gateway
      ? process.env.KITS_GATEWAY_MODEL || DEFAULT_GATEWAY_MODEL
      : process.env.OPENAI_MODEL,
    baseUrl:
      gateway?.baseUrl ??
      process.env.OPENAI_BASE_URL ??
      'https://api.openai.com/v1',
    webSearchProvider: webSearchProvider(process.env.WEB_SEARCH_PROVIDER),
    parallelApiKey: process.env.PARALLEL_API_KEY,
    browserUrl: process.env.BROWSER_URL,
    browserSecret: process.env.BROWSER_SECRET,
    computerSupervisorUrl: process.env.COMPUTER_SUPERVISOR_URL,
    computerSupervisorToken: process.env.COMPUTER_SUPERVISOR_TOKEN,
    computerToken: process.env.COMPUTER_TOKEN,
    computerNamespace: process.env.COMPUTER_NAMESPACE,
    voiceKey: process.env.VOICE_API_KEY,
    voiceModel: process.env.VOICE_MODEL,
    voiceName: process.env.VOICE_NAME ?? 'marin',
    slackChannel: process.env.SLACK_CHANNEL_NAME,
    slackTeam: process.env.SLACK_TEAM_ID,
    slackUsers: (process.env.SLACK_USER_IDS ?? '')
      .split(',')
      .map((value) => value.trim())
      .filter(Boolean),
    slackDotId: process.env.SLACK_DOT_ID || undefined,
    runtimeUrl: `http://${host === '::1' ? '[::1]' : '127.0.0.1'}:${port}/api/copilotkit`,
    ownerToken,
  };
}

/** Yarıda kalan denemeden sonra işi baştan değil kaldığı yerden sürdürt. */
export function resumablePrompt(prompt: string, note?: string): string {
  if (!note) return prompt;
  return `${prompt}\n\n[Devam] Bu görevin önceki denemesi yarıda kesildi. O denemenin son ilerleme kayıtları:\n${note}\nDiskte ve konuşmada zaten yapılmış işi kontrol et; tamamlananları tekrarlama, kaldığın yerden devam et.`;
}

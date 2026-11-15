import { TaskRunPolicy } from './task-run-policy.js';
import { ConversationService } from './conversation-service.js';
import type { Claim } from './store.js';
import type { KitHostDependencies } from './kit-host.js';
import { FusionService } from './fusion/service.js';
import { ComputerService } from './computer-service.js';
import { PageService } from './page-service.js';
import {
  CopilotKitIntelligence,
  CopilotRuntime,
  createCopilotHonoHandler,
  type CopilotHonoApp,
} from '@copilotkit/runtime/v2';
import { createSlackChannel } from './slack-channel.js';
export { slackIdentity } from './slack-channel.js';
import { Store } from './store.js';
import { WorkspaceStore } from './workspace.js';
import { DotAgent } from './dot-agent.js';
import { runThreadTurn } from './headless.js';
import { setupStatus, type PlatformConfig } from './platform-config.js';
import { validateRuntimeScope } from './runtime-scope.js';
import { learningSelector } from './learning.js';
import { LocalThreadRunner } from './local-threads.js';
import { restoreThreadBinding } from './thread-restore.js';
export class Platform {
  private channelStartupFailed = false;
  private readonly taskRuns: TaskRunPolicy;
  private readonly conversations: ConversationService;
  readonly pages: PageService;
  readonly fusion: FusionService;
  readonly computers: ComputerService;
  readonly intelligence?: CopilotKitIntelligence;
  /** Dış sohbet servisi yokken kullanılan yerel, kalıcı sohbet deposu. */
  readonly localThreads?: LocalThreadRunner;
  readonly handler?: CopilotHonoApp;
  constructor(
    readonly store: Store,
    readonly workspace: WorkspaceStore,
    readonly config: PlatformConfig,
    readonly host?: KitHostDependencies,
  ) {
    this.taskRuns = new TaskRunPolicy(store, workspace);
    this.conversations = new ConversationService(
      workspace,
      () => {
        if (this.localThreads)
          return {
            kind: 'local',
            ensure: (id, dotId) => this.localThreads!.ensureThread(id, dotId),
          };
        if (!this.intelligence)
          throw new Error('Sohbet sağlayıcısı bağlı değil.');
        return {
          kind: 'remote',
          create: (input) => this.intelligence!.createThread(input),
          read: (input) => this.intelligence!.getThread(input),
        };
      },
      () => this.requireReady(),
    );
    this.fusion = new FusionService(
      workspace,
      () => store.settings().paused,
      config.fusion,
      undefined,
      store,
    );
    this.computers = new ComputerService(
      workspace,
      config,
      () => store.settings().paused,
    );
    this.pages = new PageService(workspace, () => {
      this.requireReady();
      return this.intelligence ?? this.localPageThreads();
    });
    if (!config.intelligenceKey) {
      if (!config.localThreadsPath) return;
      this.localThreads = new LocalThreadRunner(
        config.localThreadsPath,
        workspace.ownerId,
        (threadId) =>
          workspace.conversations().find((thread) => thread.id === threadId)
            ?.title ?? null,
      );
      // Yerel kip: SSE çalışma zamanı + diske yazan koşucu. Slack kanalı ve
      // öğrenilmiş beceri teslimi Intelligence gerektirir; burada kapalıdır.
      const local = new CopilotRuntime({
        runner: this.localThreads,
        agents: async () =>
          Object.fromEntries(
            workspace
              .dots()
              .map((dot) => [
                dot.id,
                new DotAgent(
                  store,
                  workspace,
                  config,
                  dot.id,
                  false,
                  this.fusion,
                  host?.localComputerPolicy,
                  this.taskRuns,
                ),
              ]),
          ),
      });
      this.handler = createCopilotHonoHandler({
        runtime: local,
        basePath: '/api/copilotkit',
        cors: { origin: [] },
      });
      return;
    }
    this.intelligence = new CopilotKitIntelligence({
      apiKey: config.intelligenceKey,
      apiUrl: config.intelligenceApiUrl,
      wsUrl: config.intelligenceWsUrl,
      getLearningContainerId: learningSelector(
        workspace,
        config.slackDotId ?? workspace.dots()[0]?.id,
      ),
    });
    const channels = [];
    if (config.slackChannel && config.slackTeam && config.slackUsers.length) {
      const dotId = config.slackDotId ?? workspace.dots()[0].id;
      if (!workspace.dot(dotId))
        throw new Error('SLACK_DOT_ID var olan bir Kit’i göstermiyor.');
      const slack = createSlackChannel({
        name: config.slackChannel,
        config,
        ownerId: workspace.ownerId,
        paused: () => store.settings().paused,
        agent: () =>
          new DotAgent(
            store,
            workspace,
            config,
            dotId,
            true,
            this.fusion,
            host?.localComputerPolicy,
            this.taskRuns,
          ),
      });
      channels.push(slack);
    }
    const runtime = new CopilotRuntime({
      intelligence: this.intelligence,
      identifyUser: async () => ({
        id: workspace.ownerId,
        name: 'Kits sahibi',
      }),
      agents: async () =>
        Object.fromEntries(
          workspace
            .dots()
            .map((dot) => [
              dot.id,
              new DotAgent(
                store,
                workspace,
                config,
                dot.id,
                false,
                this.fusion,
                host?.localComputerPolicy,
                this.taskRuns,
              ),
            ]),
        ),
      channels,
      generateThreadNames: true,
    });
    this.handler = createCopilotHonoHandler({
      runtime,
      basePath: '/api/copilotkit',
      cors: { origin: [] },
    });
  }
  setup() {
    return setupStatus(
      this.config,
      this.handler?.channels?.status().overall ??
        (this.config.slackChannel ? 'setup_required' : 'not_configured'),
      this.channelStartupFailed,
    );
  }
  private localPageThreads() {
    const runner = this.localThreads!;
    return {
      getOrCreateThread: async (input: { threadId: string; agentId: string }) =>
        runner.ensureThread(input.threadId, input.agentId),
      getThreadMessages: async (input: { threadId: string }) => ({
        messages: runner.getThreadMessages(input.threadId),
      }),
    };
  }
  requireReady() {
    const missing = this.setup().missing;
    if (missing.length)
      throw new Error(
        `Kurulum gerekli: ${missing.join(', ')}. Sohbetler için bir sohbet deposu gerekir.`,
      );
  }
  async start() {
    if (this.handler?.channels) {
      try {
        await this.handler.channels.ready({ timeoutMs: 15000 });
        this.channelStartupFailed = false;
      } catch (error) {
        this.channelStartupFailed = true;
        throw error;
      }
    }
  }
  async stop() {
    await this.fusion.stop();
    await this.conversations.close();
    await this.handler?.channels?.stop();
  }
  async createConversation(dotId: string, title: string, requestId?: string) {
    return this.conversations.create(dotId, title, requestId);
  }
  async importConversation(dotId: string, threadId: string) {
    this.requireReady();
    return restoreThreadBinding(
      this.workspace,
      threadId,
      dotId,
      async (input) => {
        if (this.localThreads) {
          const thread = this.localThreads
            .listThreads()
            .find((item) => item.id === input.threadId);
          if (!thread) throw new Error('Sohbet bulunamadı.');
          return thread;
        }
        if (!this.intelligence)
          throw new Error('Sohbet bağlantısı kullanılamıyor.');
        return this.intelligence.getThread(input);
      },
    );
  }
  async history(threadId: string): Promise<string> {
    this.requireReady();
    this.workspace.requireThread(threadId);
    const history = this.localThreads
      ? { messages: this.localThreads.getThreadMessages(threadId) }
      : await this.intelligence!.getThreadMessages({
          threadId,
          userId: this.workspace.ownerId,
        });
    return history.messages
      .filter((message) => ['user', 'assistant'].includes(message.role))
      .slice(-12)
      .map(
        (message) =>
          `${message.role}: ${typeof message.content === 'string' ? message.content : ''}`,
      )
      .join('\n')
      .slice(-12000);
  }
  async handle(request: Request): Promise<Response> {
    if (!this.handler)
      return Response.json(
        { error: 'Kurulum gerekli: sohbet deposu.' },
        { status: 503 },
      );
    let body: unknown;
    if (request.method !== 'GET' && request.method !== 'HEAD')
      body = await request
        .clone()
        .json()
        .catch(() => null);
    try {
      validateRuntimeScope(request, this.workspace, body);
    } catch (error) {
      return Response.json(
        {
          error:
            error instanceof Error
              ? error.message
              : 'Sohbet kapsamı reddedildi.',
        },
        { status: 403 },
      );
    }
    return this.handler.fetch(request);
  }
  async runTaskTurn(
    claim: Claim,
    prompt: string,
    signal: AbortSignal,
    progress?: (text: string) => void,
  ): Promise<string> {
    const unregister = this.taskRuns.register(claim);
    try {
      const threadId = this.workspace.taskThread(claim.id)!;
      const text = await this.turn(
        threadId,
        prompt,
        signal,
        undefined,
        progress,
        claim.lease,
      );
      this.taskRuns
        .resolve({
          ownerId: this.workspace.ownerId,
          dotId: this.workspace.requireThread(threadId).dotId,
          threadId,
          runId: claim.lease,
        })!
        .check();
      signal.throwIfAborted();
      return text;
    } finally {
      unregister();
    }
  }
  async turn(
    threadId: string,
    prompt: string,
    signal: AbortSignal,
    metadata?: Record<string, unknown>,
    progress?: (text: string) => void,
    runId?: string,
  ): Promise<string> {
    this.requireReady();
    const thread = this.workspace.requireThread(threadId);
    return runThreadTurn(
      this.config.runtimeUrl,
      this.config.ownerToken
        ? { Authorization: `Bearer ${this.config.ownerToken}` }
        : {},
      thread.dotId,
      threadId,
      prompt,
      signal,
      metadata,
      this.localThreads?.getThreadMessages(threadId),
      progress,
      runId,
    );
  }
}

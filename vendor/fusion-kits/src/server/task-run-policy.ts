import type { ToolDefinition } from '@copilotkit/runtime/v2';
import type { TaskIntent } from '../shared/types.js';
import { Store, type Claim } from './store.js';
import { WorkspaceStore } from './workspace.js';

interface RunIdentity {
  readonly ownerId: string;
  readonly dotId: string;
  readonly threadId: string;
  readonly runId: string;
}
export interface TaskRunScope {
  readonly intent: TaskIntent;
  check(): void;
  tools(tools: ToolDefinition[]): ToolDefinition[];
}
const researchReads = new Set([
  'search_web',
  'read_public_page',
  'list_authorized_spaces',
  'list_space_pages',
  'read_space_page',
]);
interface RegisteredRun extends RunIdentity {
  readonly claim: Claim;
}
/** Authority stays in host memory and the existing SQLite claim, never model input. */
export class TaskRunPolicy {
  private readonly runs = new Map<string, RegisteredRun>();
  constructor(
    private store: Store,
    private workspace: WorkspaceStore,
  ) {}
  register(claim: Claim): () => void {
    const task = this.store.task(claim.id);
    if (
      !task ||
      !this.store.owns(claim) ||
      task.intent !== claim.intent ||
      !task.leaseUntil ||
      task.leaseUntil <= Date.now()
    )
      throw new Error('Görev koşusu artık yetkili değil.');
    const threadId = this.workspace.taskThread(claim.id);
    if (!threadId) throw new Error('Görevin sohbet kapsamı yok.');
    const thread = this.workspace.requireThread(threadId);
    if (this.runs.has(claim.lease))
      throw new Error('Görev koşusu zaten kayıtlı.');
    const run: RegisteredRun = {
      claim: { ...claim },
      threadId,
      dotId: thread.dotId,
      ownerId: this.workspace.ownerId,
      runId: claim.lease,
    };
    this.runs.set(claim.lease, run);
    return () => {
      if (this.runs.get(claim.lease) === run) this.runs.delete(claim.lease);
    };
  }
  resolve(identity: RunIdentity): TaskRunScope | undefined {
    const run = this.runs.get(identity.runId);
    if (!run) {
      // A missing/wrong run ID cannot downgrade an active proactive turn to manual.
      if (
        this.store.taskForRun(identity.runId) ||
        [...this.runs.values()].some(
          (active) =>
            active.threadId === identity.threadId &&
            active.claim.intent === 'proactive_research',
        )
      )
        throw new Error('Görev koşusu kapsamı eksik veya geçersiz.');
      return undefined;
    }
    const check = () => {
      if (
        this.runs.get(identity.runId) !== run ||
        identity.ownerId !== run.ownerId ||
        identity.dotId !== run.dotId ||
        identity.threadId !== run.threadId ||
        identity.runId !== run.claim.lease ||
        this.workspace.ownerId !== run.ownerId ||
        this.workspace.taskThread(run.claim.id) !== run.threadId ||
        this.store.taskForRun(identity.runId)?.id !== run.claim.id ||
        this.store.task(run.claim.id)?.intent !== run.claim.intent ||
        !this.store.owns(run.claim) ||
        (this.store.task(run.claim.id)?.leaseUntil ?? 0) <= Date.now()
      )
        throw new Error('Görev koşusu izni veya kirası iptal edildi.');
      this.workspace.requireThread(run.threadId, run.dotId);
    };
    check();
    return {
      intent: run.claim.intent,
      check,
      tools: (tools) =>
        tools
          .filter(
            (tool) =>
              run.claim.intent !== 'proactive_research' ||
              researchReads.has(tool.name),
          )
          .map((tool) => {
            const execute = tool.execute;
            if (!execute) throw new Error(`Araç yürütücüsü yok: ${tool.name}`);
            return {
              ...tool,
              execute: async (input: unknown) => {
                check();
                const result = await execute(input);
                check();
                return result;
              },
            };
          }),
    };
  }
}

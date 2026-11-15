import type { WorkspaceStore } from './workspace.js';
import { boundedIntelligence } from './intelligence-deadline.js';

export class ThreadBindingError extends Error {
  constructor(
    message: string,
    readonly status: 403 | 503,
  ) {
    super(message);
  }
}
export interface ThreadMetadata {
  id: string;
  agentId?: string;
  createdById?: string;
  name: string | null;
  archived?: boolean;
}
export async function restoreThreadBinding(
  workspace: WorkspaceStore,
  id: string,
  dotId: string,
  read: (input: {
    threadId: string;
    userId: string;
  }) => Promise<ThreadMetadata>,
) {
  const bound = () =>
    workspace.conversations().find((thread) => thread.id === id);
  const check = (thread: NonNullable<ReturnType<typeof bound>>) => {
    if (thread.dotId !== dotId)
      throw new ThreadBindingError('Sohbet farklı bir Kit’e ait.', 403);
    return thread;
  };
  if (!workspace.dot(dotId))
    throw new ThreadBindingError('Kit bulunamadı.', 403);
  const existing = bound();
  if (existing) return check(existing);
  const remote = await verifiedThreadMetadata(workspace, id, dotId, read);
  const current = bound();
  if (current) return check(current);
  try {
    return workspace.bindThread(
      id,
      dotId,
      remote.name?.trim() || 'Adsız sohbet',
    );
  } catch (error) {
    const concurrent = bound();
    if (concurrent) return check(concurrent);
    throw error;
  }
}

export async function verifiedThreadMetadata(
  workspace: WorkspaceStore,
  id: string,
  dotId: string,
  read: (input: {
    threadId: string;
    userId: string;
  }) => Promise<ThreadMetadata>,
): Promise<ThreadMetadata> {
  let remote: ThreadMetadata;
  try {
    remote = await boundedIntelligence(
      read({ threadId: id, userId: workspace.ownerId }),
    );
  } catch {
    throw new ThreadBindingError(
      'Uzak sohbet doğrulanamadı; bağlantıyı yeniden dene.',
      503,
    );
  }
  if (
    remote.id !== id ||
    remote.agentId !== dotId ||
    remote.createdById !== workspace.ownerId ||
    remote.archived === true
  ) {
    throw new ThreadBindingError(
      'Sohbetin kullanıcı ve Kit kapsamı doğrulanamadı.',
      403,
    );
  }
  return remote;
}

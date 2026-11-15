import type { Conversation } from '../shared/types';

interface RemoteThread {
  id: string;
  name?: string | null;
  agentId?: string;
  archived?: boolean;
  updatedAt?: string;
  createdAt?: string;
}
export function mergeThreadRows(
  local: Conversation[],
  remote: RemoteThread[],
  dotId: string,
) {
  const rows = new Map(
    local.map((thread) => [
      thread.id,
      {
        id: thread.id,
        dotId: thread.dotId,
        title: thread.title,
        activity: thread.createdAt,
      },
    ]),
  );
  for (const thread of remote) {
    if (thread.archived || (thread.agentId && thread.agentId !== dotId))
      continue;
    const existing = rows.get(thread.id);
    if (existing && existing.dotId !== dotId) continue;
    const timestamp = Date.parse(thread.updatedAt || thread.createdAt || '');
    rows.set(thread.id, {
      id: thread.id,
      dotId,
      title: thread.name || existing?.title || 'Adsız sohbet',
      activity: Number.isFinite(timestamp)
        ? timestamp
        : existing?.activity || 0,
    });
  }
  return [...rows.values()].sort(
    (a, b) => b.activity - a.activity || a.id.localeCompare(b.id),
  );
}

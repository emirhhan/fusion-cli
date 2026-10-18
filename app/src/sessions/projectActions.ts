import type { ProjectRecord } from "./projectRecords";

interface ProjectActions {
  createChat(input: { root: string; mode: "kod" }): Promise<string>;
  desktopRoot(): Promise<string>;
  assign(chatId: string, projectId: string): void;
}

export class ProjectOpenError extends Error {
  constructor(public readonly projectId: string, cause: unknown) {
    super(`Proje kaydedildi fakat sohbet açılamadı: ${cause instanceof Error ? cause.message : String(cause)}`);
  }
}

export async function openProjectChat(record: ProjectRecord, actions: ProjectActions): Promise<string> {
  const root = record.root || await actions.desktopRoot();
  const id = await actions.createChat({ root, mode: "kod" });
  actions.assign(id, record.id);
  return id;
}

export async function createAndOpenProject(
  input: { name: string; root?: string },
  actions: ProjectActions & { createRecord(input: { name: string; root?: string }): string },
): Promise<string> {
  const id = actions.createRecord(input);
  try {
    return await openProjectChat({ ...input, id, createdAt: Date.now() }, actions);
  } catch (cause) {
    throw new ProjectOpenError(id, cause);
  }
}

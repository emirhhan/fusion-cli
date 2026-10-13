/** A model label is authoritative only for the same session and transport owner. */
export interface OwnedModelSnapshot {
  sessionId: string;
  client: object;
  model: string;
  label: string;
}
const UNKNOWN_MODEL = Object.freeze({ model: "", label: "" });
export function visibleModelForSession(
  snapshot: OwnedModelSnapshot | null,
  sessionId: string | undefined,
  client: object | undefined,
): Readonly<{ model: string; label: string }> {
  if (!snapshot || !sessionId || !client || snapshot.sessionId !== sessionId || snapshot.client !== client) {
    return UNKNOWN_MODEL;
  }
  return { model: snapshot.model, label: snapshot.label };
}

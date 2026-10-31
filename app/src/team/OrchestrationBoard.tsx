import type { Mesaj } from "../screens/Conversation";
import { WorkflowBoard } from "./WorkflowBoard";

/** Ekip mesajının üstündeki pano: iş akışı (P-062); ekip mesajında pano yoksa hiçbir şey. */
export function OrchestrationBoard({ message, running }: { message: Mesaj; running: boolean }) {
  if (message.akis) return <WorkflowBoard akis={message.akis} running={running} />;
  return null;
}

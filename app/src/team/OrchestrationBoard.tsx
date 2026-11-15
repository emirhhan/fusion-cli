import type { Mesaj } from "../screens/Conversation";
import { TeamBoard } from "./TeamBoard";
import { WorkflowBoard } from "./WorkflowBoard";

/** Ekip mesajının üstündeki pano: iş akışı (P-062) ya da ekip (P-061); yoksa hiçbir şey. */
export function OrchestrationBoard({ message, running }: { message: Mesaj; running: boolean }) {
  if (message.akis) return <WorkflowBoard akis={message.akis} running={running} />;
  if (message.pano) return <TeamBoard pano={message.pano} running={running} />;
  return null;
}

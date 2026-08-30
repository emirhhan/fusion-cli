import type { ProcessController } from "./useProcesses";
import { TerminalTabs } from "./TerminalTabs";
import "./processes.css";

export function TerminalPanel({ controller }: { controller: ProcessController }) {
  return <TerminalTabs controller={controller} />;
}

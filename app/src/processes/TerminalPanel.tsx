import { TerminalTabs } from "./TerminalTabs";
import type { TerminalRuntime } from "./terminalBridge";
import "./processes.css";

export function TerminalPanel({ cwd, runtime }: { cwd: string; runtime?: TerminalRuntime }) {
  return <TerminalTabs cwd={cwd} runtime={runtime} />;
}

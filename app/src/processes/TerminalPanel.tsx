import { TerminalTabs } from "./TerminalTabs";
import "./processes.css";

export function TerminalPanel({ cwd }: { cwd: string }) {
  return <TerminalTabs cwd={cwd} />;
}

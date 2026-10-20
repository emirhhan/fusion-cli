import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { Composer } from "../src/screens/Composer";
import "../src/theme/tokens.css";
import "../src/brand/fonts.css";
document.documentElement.dataset.theme = new URLSearchParams(location.search).get("theme") ?? "dark";
function Preview() {
 const [mode, setMode] = useState<"steer" | "queue">("steer");
 return <main style={{ containerType: "inline-size", containerName: "conversation-workspace", display: "grid", alignContent: "end", minHeight: "100dvh", background: "var(--surface-canvas)" }}><Composer onApprovalChange={() => {}} onWorkspaceModeChange={() => {}} running busySubmissionMode={mode} onBusySubmissionModeChange={setMode} onSend={() => undefined} activeModel="nemotron-3-super" onModelSelect={() => {}} workspaceMode="sohbet" /></main>;
}
createRoot(document.getElementById("root")!).render(<Preview />);

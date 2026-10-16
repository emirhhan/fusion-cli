import React from "react";
import { createRoot } from "react-dom/client";
import { PermissionPrompt } from "../src/permissions/PermissionPrompt";
import "../src/theme/tokens.css";
document.documentElement.dataset.theme = new URLSearchParams(location.search).get("theme") ?? "dark";
createRoot(document.getElementById("root")!).render(<PermissionPrompt kind="microphone" phase="denied" canOpenSettings onContinue={() => {}} onRetry={() => {}} onOpenSettings={() => {}} onDismiss={() => {}} />);

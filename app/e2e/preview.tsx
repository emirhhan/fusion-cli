import React from "react";
import ReactDOM from "react-dom/client";
import "../src/theme/tokens.css";
import "../src/App.css";
import { Approval } from "../src/dialogs/Approval";
import { AppHeader } from "../src/screens/AppHeader";
import { Composer } from "../src/screens/Composer";
import { Conversation } from "../src/screens/Conversation";
import { EmptyState } from "../src/screens/EmptyState";
import { Inspector } from "../src/screens/Inspector";
import { Shell } from "../src/screens/Shell";
import { Sidebar } from "../src/screens/Sidebar";
import { applyTheme, type ThemePreference } from "../src/theme/theme";

const params = new URLSearchParams(location.search);
const theme = (params.get("theme") ?? "light") as ThemePreference;
const state = params.get("state") ?? "conversation";
const inspectorOpen = params.get("inspector") !== "0";
applyTheme(theme);

const messages = [
  { rol: "kullanici" as const, metin: "Fusion için profesyonel bir macOS uygulaması hazırla." },
  { rol: "olay" as const, metin: "7 arayüz testi ve üretim derlemesi tamamlandı" },
  { rol: "asistan" as const, metin: "Uygulama kabuğunu tamamladım. Sol navigasyon, konuşma alanı ve bağlamsal denetçi aynı tasarım sistemiyle çalışıyor.\n\nAçık ve koyu tema ile dar pencere davranışları da doğrulandı." },
];

function Preview() {
  return (
    <>
      <Shell
        composer={<Composer onSend={() => undefined} />}
        content={state === "empty" ? <EmptyState /> : <Conversation mesajlar={messages} />}
        header={<AppHeader inspectorOpen={inspectorOpen} onToggleInspector={() => undefined} onToggleSidebar={() => undefined} projectName="fusion-cli" sidebarCollapsed={false} status="Hazır" themePreference={theme} title="macOS uygulaması" />}
        inspector={<Inspector />}
        inspectorOpen={inspectorOpen}
        sidebar={<Sidebar availableSources={["claude", "codex"]} etkin="1" onSec={() => undefined} onYeni={() => undefined} oturumlar={[{ session_id: "1", source: "fusion", title: "macOS uygulaması" }, { session_id: "2", source: "claude", title: "Fusion CLI testleri" }]} />}
      />
      {state === "approval" && <Approval onCevap={() => undefined} soru={{ tur: "onay", arac: "write_file", argumanlar: { path: "app/src/App.tsx" }, tehlike: null, onerilen: "once", secenekler: [{ deger: "deny", etiket: "Reddet" }, { deger: "once", etiket: "Bir kez izin ver" }] }} />}
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><Preview /></React.StrictMode>);

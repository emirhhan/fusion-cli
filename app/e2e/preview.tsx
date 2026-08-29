import React from "react";
import ReactDOM from "react-dom/client";
import "../src/theme/tokens.css";
import "../src/App.css";
import { Approval } from "../src/dialogs/Approval";
import { HistoryPicker } from "../src/dialogs/HistoryPicker";
import type { HistoryController } from "../src/history/useHistory";
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

const historySession = {
  kaynak: "claude" as const,
  oturum_id: "claude-fusion-app",
  baslik: state === "history-long"
    ? "Fusion masaüstü uygulamasının tüm ekranları, çoklu oturum mimarisi ve profesyonel dağıtım akışı"
    : "Fusion macOS uygulaması",
  guncellendi: 1_788_000_000,
  tur_sayisi: 18,
  boyut: 24_500,
};

function historyFixture(): HistoryController {
  const selected = ["history-preview", "history-warning", "history-long"].includes(state)
    ? historySession
    : null;
  return {
    error: state === "history-error" ? "Claude geçmişi şu anda okunamadı. Tekrar deneyebilirsiniz." : null,
    loadMoreSessions: async () => undefined,
    loadMoreTurns: async () => undefined,
    loading: false,
    openSource: async () => undefined,
    selected,
    selectSession: async () => undefined,
    sessionCursor: state === "history-preview" ? 30 : null,
    sessions: state === "history-empty" ? [] : [
      historySession,
      { ...historySession, oturum_id: "claude-game", baslik: "Tarayıcı oyunu ve görsel varlıklar", tur_sayisi: 9 },
      { ...historySession, oturum_id: "claude-tests", baslik: "Fusion CLI test sözleşmeleri", tur_sayisi: 27 },
    ],
    source: state === "history-source" ? null : "claude",
    sources: [
      { ad: "claude", komut: "/resumeclaude" },
      { ad: "codex", komut: "/resumecodex" },
    ],
    turnCursor: state === "history-preview" ? 30 : null,
    turns: selected ? [
      { rol: "user", metin: "Fusion uygulamasını profesyonel bir macOS ürünü olarak tamamla.", zaman: 1_787_999_800 },
      { rol: "assistant", metin: state === "history-long"
        ? "Çoklu oturum yöneticisini, geçmiş kaynak seçicisini, güvenli metadata kalıcılığını ve paketli çalışma zamanını tek mimaride doğruluyorum. Bu uzun yanıt dar alanlarda taşmadan okunabilmeli."
        : "Çoklu oturum ve geçmiş seçme akışını tamamlıyorum.", zaman: 1_787_999_900 },
    ] : [],
  };
}

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
      {state.startsWith("history-") && (
        <HistoryPicker
          history={historyFixture()}
          onClose={() => undefined}
          onResume={async () => ({ id: "resumed", secretCount: state === "history-warning" ? 2 : 0 })}
          open
        />
      )}
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(<React.StrictMode><Preview /></React.StrictMode>);

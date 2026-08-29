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
import { FileExplorer } from "../src/workspace/FileExplorer";
import { ChangesPanel } from "../src/workspace/ChangesPanel";
import { PreviewPanel } from "../src/workspace/PreviewPanel";
import { TestsPanel } from "../src/workspace/TestsPanel";
import { TerminalPanel } from "../src/processes/TerminalPanel";
import { ProcessesPanel } from "../src/processes/ProcessesPanel";
import type { ProcessController } from "../src/processes/useProcesses";
import type { ProtocolClient } from "../src/protocol/client";
import { SkillsCatalog } from "../src/capabilities/SkillsCatalog";

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

const workspaceProcesses = [{
  surec_id: "visual-tests", komut: "npm test", cwd: ".", pid: 4312,
  durum: state === "workspace-error" ? "hata" as const : "bitti" as const,
  cikis_kodu: state === "workspace-error" ? 1 : 0,
  cikti: state === "workspace-error" ? "FAIL src/App.test.tsx\n1 test failed" : "100 tests passed\n✓ production build ready",
  baslangic: 1_788_000_000,
}];
const processController = {
  busy: false, error: null, processes: workspaceProcesses,
  refresh: async () => undefined, start: async () => undefined, stop: async () => undefined,
} as ProcessController;

const workspaceClient = {
  request: async (name: string, data: Record<string, unknown>) => {
    if (name === "proje.durum") return { ok: true, kok: "/Projects/fusion-cli", git: true, okunabilir: true, yazilabilir: true };
    if (name === "proje.listele") {
      if (data.yol === "assets") return { ok: true, girdiler: [{ ad: "fusion-preview.svg", yol: "assets/fusion-preview.svg", tur: "dosya", boyut: 205, degistirilme: 1 }], next_cursor: null, has_more: false };
      if (data.yol === "src") return { ok: true, girdiler: [{ ad: "app.py", yol: "src/app.py", tur: "dosya", boyut: 422, degistirilme: 1 }], next_cursor: null, has_more: false };
      return { ok: true, girdiler: [
        { ad: "assets", yol: "assets", tur: "klasor", boyut: 0, degistirilme: 1 },
        { ad: "src", yol: "src", tur: "klasor", boyut: 0, degistirilme: 1 },
        { ad: "README.md", yol: "README.md", tur: "dosya", boyut: 5820, degistirilme: 1 },
      ], next_cursor: null, has_more: false };
    }
    if (name === "proje.oku") return { ok: true, yol: String(data.yol), tur: String(data.yol).endsWith(".svg") ? "metin" : "metin", mime: String(data.yol).endsWith(".svg") ? "image/svg+xml" : "text/markdown", boyut: 5820, sha256: "visual", icerik: "# Fusion App\n\nProfesyonel macOS çalışma alanı\n\n" + Array.from({ length: 28 }, (_, index) => `${index + 1}. Dosyalar, terminal, testler ve önizleme aynı güvenli oturumda çalışır.`).join("\n"), kesildi: false };
    if (name === "proje.degisiklikler") return { ok: true, degisiklikler: [{ yol: "src/app.py", added: 5, removed: 2, geri_alinabilir: true, diff: "--- a/src/app.py\n+++ b/src/app.py\n@@ -1,2 +1,5 @@\n-print('old')\n+print('Fusion hazır')\n+run_tests()\n+open_preview()" }] };
    if (name === "proje.komut_onerileri") return { ok: true, komutlar: [{ tur: "check", ad: "Tüm kalite kapısı", komut: "make check" }, { tur: "build", ad: "Üretim derlemesi", komut: "npm run build" }] };
    if (name === "proje.git_durum") return { ok: true, git: true, branch: "fusion-app", degisen: 3, ileride: 2, geride: 0 };
    if (name === "proje.onizle") return { ok: true, yol: String(data.yol), tur: "image", mime: "image/svg+xml", boyut: 205, base64: btoa('<svg xmlns="http://www.w3.org/2000/svg" width="720" height="420"><rect width="100%" height="100%" rx="24" fill="#101828"/><circle cx="360" cy="180" r="88" fill="#10a37f"/><text x="360" y="320" text-anchor="middle" fill="white" font-size="34" font-family="sans-serif">Fusion App</text></svg>') };
    if (name === "yetenek.katalog") return { ok: true,
      beceriler: [
        { ad: "frontend-design", aciklama: "Üretim kalitesinde arayüz tasarım disiplini", kaynak: "claude+codex", tur: "beceri", etkin: true, izinler: ["dosya okuma", "dosya düzenleme"] },
        { ad: "systematic-debugging", aciklama: "Kanıta dayalı hata ayıklama", kaynak: "claude", tur: "beceri", etkin: true, izinler: ["dosya okuma", "komut çalıştırma"] },
      ],
      ajanlar: [{ ad: "architect", aciklama: "Mimari kararları ve sınırları inceler", kaynak: "codex", tur: "ajan", etkin: true, izinler: ["dosya okuma"] }],
      talimatlar: [{ ad: "CLAUDE.md", aciklama: "Aktif proje talimatı", kaynak: "proje", tur: "talimat", etkin: true, izinler: [] }],
      mcp: [{ ad: "figma", aciklama: "Figma tasarım dosyaları ve düğümleri", kaynak: "fusion", tur: "mcp", etkin: false, izinler: ["yerel komut", "dış araçlar"] }],
    };
    if (name === "yetenek.detay") return { ok: true, tur: data.tur, ad: data.ad, icerik: "Bu uzmanlık, görevin gerektirdiği dosyaları önce okur; değişiklikten sonra test ve görsel kanıt toplar.", kesildi: false };
    return { ok: true };
  },
} as unknown as ProtocolClient;

function WorkspaceInspector() {
  const [selected, setSelected] = React.useState<string | null>(null);
  return <Inspector content={{
    files: <FileExplorer client={workspaceClient} onSelected={setSelected} root="/Projects/fusion-cli" />,
    changes: <ChangesPanel client={workspaceClient} revision={0} />,
    terminal: <TerminalPanel controller={processController} />,
    processes: <ProcessesPanel controller={processController} />,
    tests: <TestsPanel client={workspaceClient} processes={processController} />,
    preview: <PreviewPanel client={workspaceClient} selectedPath={selected} />,
    context: <div><strong>Aktif bağlam</strong><p>CLAUDE.md · 4 skill · 2 MCP sunucusu</p></div>,
  }} />;
}

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
  const inspector = state.startsWith("workspace-") ? <WorkspaceInspector /> : <Inspector />;
  const capabilities = state === "capabilities";
  return (
    <>
      <Shell
        composer={capabilities ? undefined : <Composer onSend={() => undefined} />}
        content={capabilities ? <SkillsCatalog client={workspaceClient} onClose={() => undefined} /> : state === "empty" ? <EmptyState /> : <Conversation mesajlar={messages} />}
        header={<AppHeader inspectorOpen={!capabilities && inspectorOpen} onToggleInspector={() => undefined} onToggleSidebar={() => undefined} projectName="fusion-cli" sidebarCollapsed={false} status="Hazır" themePreference={theme} title={capabilities ? "Beceriler ve Ajanlar" : "macOS uygulaması"} />}
        inspector={capabilities ? undefined : inspector}
        inspectorOpen={!capabilities && inspectorOpen}
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

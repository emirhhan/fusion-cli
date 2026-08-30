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
import { ControlPanel } from "../src/control/ControlPanel";
import { Lessons } from "../src/lessons/Lessons";
import { Settings } from "../src/settings/Settings";
import { Onboarding, type OnboardingValue } from "../src/onboarding";

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
    if (name === "ders.listele") return { ok: true, dersler: [
      { id: "ilk-proje", baslik: "İlk proje", ozet: "Boş bir klasörden gerçek bir projeye ilk adımı at.", adim_sayisi: 2 },
      { id: "basit-oyun-veya-site", baslik: "Basit oyun veya web sitesi", ozet: "Tek dosyalık küçük bir oyun ya da sayfa üret ve sonucu izle.", adim_sayisi: 2 },
      { id: "varlik-ekleme-onizleme", baslik: "Asset ekleme ve önizleme", ozet: "Bir görsel veya ikon ekle ve sonucu önizlemede gör.", adim_sayisi: 2 },
      { id: "model-ve-dusunme-duzeyi", baslik: "Model ve düşünme düzeyi", ozet: "Hangi modelin, hakemin ve düşünme düzeyinin kullanıldığını gör.", adim_sayisi: 2 },
      { id: "izinler-ve-geri-alma", baslik: "İzinler ve geri alma", ozet: "Küçük zararsız bir değişiklik yap, sonra geri al.", adim_sayisi: 3 },
      { id: "gecmis-surdurme", baslik: "Geçmiş sürdürme", ozet: "Önceki bir oturumu bul ve kaldığın yerden devam et.", adim_sayisi: 2 },
      { id: "beceri-ve-ajan-kullanma", baslik: "Beceri ve ajan kullanma", ozet: "Katalogdaki bir beceriyi veya ajanı gör ve dene.", adim_sayisi: 2 },
      { id: "test-paketleme-paylasma", baslik: "Test etme, paketleme ve paylaşma", ozet: "Testleri çalıştır, paketleme adımlarını öğren ve paylaşmaya hazırlan.", adim_sayisi: 2 },
    ] };
    if (name === "ders.getir") return { ok: true, id: "izinler-ve-geri-alma", baslik: "İzinler ve geri alma", ozet: "Küçük zararsız bir değişiklik yap, sonra geri al.", adimlar: [
      { id: "onay-modu", baslik: "Onay modunu tanı", aciklama: "Kontrol panelinden mevcut izin/onay modunu gör.", eylem: { tur: "sekme", hedef: "kontrol" } },
      { id: "degisiklik-yap", baslik: "Küçük bir değişiklik yap", aciklama: "Zararsız, geri alınabilir küçük bir dosya değişikliği iste.", eylem: { tur: "composer", gorev: "Proje klasörüne test.txt adında zararsız, boş bir dosya ekle." } },
      { id: "geri-al", baslik: "Değişikliği geri al", aciklama: "Proje sekmesindeki değişiklikler listesinden son adımı geri al.", eylem: { tur: "sekme", hedef: "proje" } },
    ] };
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
    if (name === "kontrol.durum") return { ok: true, kok: "/Projects/fusion-cli",
      model: { agent: "openrouter/qwen3-coder", hakem: "nvidia_nim/llama-3.3-70b", adaylar: ["openrouter/deepseek-r1", "nvidia_nim/qwen3-next"], saglayici: "auto", yogunluk: "high" },
      izin: { mod: "ask", kokle_sinirli: false },
      mcp: [{ ad: "figma", komut: "npx" }, { ad: "github", komut: "docker" }],
      saglayicilar: [
        { id: "openrouter", ad: "OpenRouter", ortam: "OPENROUTER_API_KEY", kurulu: true },
        { id: "nvidia_nim", ad: "NVIDIA NIM", ortam: "NVIDIA_NIM_API_KEY", kurulu: true },
        { id: "openai", ad: "OpenAI", ortam: "OPENAI_API_KEY", kurulu: false },
        { id: "anthropic", ad: "Anthropic", ortam: "ANTHROPIC_API_KEY", kurulu: false },
      ],
      sir_deposu_hazir: true, gateway: { durum: "calisiyor", adres: "http://127.0.0.1:8787/v1", pid: 4821 },
    };
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
  const control = state === "control";
  const onboarding = state === "onboarding";
  const lessons = state === "lessons" || state === "lessons-step";
  const settings = state === "settings";
  const [onboardingValue, setOnboardingValue] = React.useState<OnboardingValue>({ step: "sources", selectedProjectId: "/Projects/fusion-cli" });
  if (onboarding) return <Onboarding value={onboardingValue} onChange={setOnboardingValue} onSkip={() => undefined} onComplete={() => undefined}
    runtime={{ status: "ready", version: "0.3.0a1" }}
    sources={[{ kind: "claude", status: "found", itemCount: 18 }, { kind: "codex", status: "found", itemCount: 24 }, { kind: "hermes", status: "not-found" }]}
    providers={[{ id: "openrouter", name: "OpenRouter", secretConfigured: true, status: "ready" }, { id: "nvidia", name: "NVIDIA NIM", secretConfigured: true, status: "ready" }]}
    projects={[{ id: "/Projects/fusion-cli", name: "fusion-cli", description: "Aktif çalışma alanı", path: "/Projects/fusion-cli" }]} />;
  return (
    <>
      <Shell
        composer={capabilities || control || lessons || settings ? undefined : <Composer onSend={() => undefined} />}
        content={settings ? <Settings client={workspaceClient} onClose={() => undefined} onThemeChange={() => undefined} themePreference={theme === "dark" ? "dark" : "light"} /> : lessons ? <Lessons client={workspaceClient} onClose={() => undefined} onOpenTab={() => undefined} onUseComposer={() => undefined} /> : capabilities ? <SkillsCatalog client={workspaceClient} onClose={() => undefined} /> : control ? <ControlPanel client={workspaceClient} onClose={() => undefined} /> : state === "empty" ? <EmptyState /> : <Conversation mesajlar={messages} />}
        header={<AppHeader inspectorOpen={!capabilities && !control && !lessons && !settings && inspectorOpen} onToggleInspector={() => undefined} onToggleSidebar={() => undefined} projectName="fusion-cli" sidebarCollapsed={false} status="Hazır" themePreference={theme} title={settings ? "Ayarlar" : lessons ? "Dersler" : capabilities ? "Beceriler ve Ajanlar" : control ? "Kontrol Paneli" : "macOS uygulaması"} />}
        inspector={capabilities || control || lessons || settings ? undefined : inspector}
        inspectorOpen={!capabilities && !control && !lessons && !settings && inspectorOpen}
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

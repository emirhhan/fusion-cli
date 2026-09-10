import { StrictMode } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";

const sidebarStyles = readFileSync(resolve(process.cwd(), "src/screens/Sidebar.css"), "utf8");

const sessions = [
  { session_id: "1", title: "İlk iş", source: "claude", project: "Şeker Oyunu" },
  { session_id: "2", title: "İkinci iş", source: "codex", project: "Kurumsal Site" },
];

afterEach(() => {
  cleanup();
  document.querySelector("[data-test-sidebar-styles]")?.remove();
});

beforeEach(() => localStorage.clear());

describe("Sidebar", () => {
  it("oturumları kaynak etiketiyle listeler", () => {
    render(<Sidebar oturumlar={sessions} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} />);
    expect(screen.getByText("İlk iş")).toBeTruthy();
    expect(screen.getByText(/claude/)).toBeTruthy();
  });

  it("etkin oturumu vurgular", () => {
    const { container } = render(
      <Sidebar oturumlar={sessions} etkin="1" onSec={vi.fn()} onYeni={vi.fn()} />,
    );
    expect(container.querySelectorAll('[data-etkin="true"]')).toHaveLength(1);
  });

  it("oturum yoksa liste başlığını basmaz", () => {
    render(<Sidebar oturumlar={[]} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} />);
    expect(screen.queryByText("Sohbetler")).toBeNull();
  });

  it("yeni sohbet tıklanınca bildirir", () => {
    const onYeni = vi.fn();
    render(<Sidebar oturumlar={[]} etkin={null} onSec={vi.fn()} onYeni={onYeni} />);
    screen.getByText("Yeni sohbet").click();
    expect(onYeni).toHaveBeenCalledOnce();
  });

  it("ürünün ana bölümlerini tek navigasyonda gösterir", () => {
    render(<Sidebar oturumlar={[]} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} />);
    expect(screen.getByRole("button", { name: /yeni sohbet/i })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /yerel profil menüsü/i }));
    expect(screen.getByRole("menuitem", { name: /beceriler ve ajanlar/i })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: /dersler/i })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: /kontrol merkezi/i })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: /mcp bağlantıları/i })).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: /ayarlar/i })).toBeTruthy();
  });

  it("profil menüsünden hedefe gider ve menüyü kapatır", () => {
    const onNavigate = vi.fn();
    render(<Sidebar oturumlar={[]} etkin={null} onNavigate={onNavigate} onSec={vi.fn()} onYeni={vi.fn()} />);

    fireEvent.click(screen.getByRole("button", { name: /yerel profil menüsü/i }));
    fireEvent.click(screen.getByRole("menuitem", { name: /mcp bağlantıları/i }));

    expect(onNavigate).toHaveBeenCalledWith("connectors");
    expect(screen.queryByRole("menu", { name: /profil menüsü/i })).toBeNull();
  });

  it("sağlayıcı girişi yokken uydurma kullanıcı adı ve paket göstermez", () => {
    render(<Sidebar oturumlar={[]} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} />);

    expect(screen.getByRole("button", { name: /yerel profil menüsü/i }).textContent).toContain("Bağlantı yok");
    expect(screen.queryByText("Emir")).toBeNull();
    expect(screen.queryByText("Plus")).toBeNull();
  });

  it("doğrulanmış web oturumunu profil satırında gerçek bağlantı olarak gösterir", () => {
    render(
      <Sidebar
        etkin={null}
        onSec={vi.fn()}
        onYeni={vi.fn()}
        oturumlar={[]}
        webProfile={{ providerName: "ChatGPT Web", account: "main" }}
      />,
    );

    const profile = screen.getByRole("button", { name: /chatgpt web profil menüsü/i });
    expect(profile.textContent).toContain("ChatGPT Web");
    expect(profile.textContent).toContain("main hesabı bağlı");
  });

  it("aramayla oturumları başlık ve kaynak üzerinden filtreler", () => {
    render(<Sidebar oturumlar={sessions} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Konuşma ve proje aramasını aç" }));
    fireEvent.change(screen.getByRole("searchbox", { name: /ara/i }), {
      target: { value: "codex" },
    });
    expect(screen.queryByText("İlk iş")).toBeNull();
    expect(screen.getByText("İkinci iş")).toBeTruthy();
  });

  it("Türkçe proje adıyla arar", () => {
    render(<Sidebar oturumlar={sessions} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Konuşma ve proje aramasını aç" }));
    fireEvent.change(screen.getByRole("searchbox", { name: /ara/i }), {
      target: { value: "şeker" },
    });
    expect(screen.getByText("İlk iş")).toBeTruthy();
    expect(screen.queryByText("İkinci iş")).toBeNull();
  });

  it("sabit ve yakın projeleri kendi bölümlerinde güncellik sırasıyla gösterir", () => {
    render(
      <Sidebar
        etkin={null}
        onSec={vi.fn()}
        onYeni={vi.fn()}
        oturumlar={[]}
        projeler={[
          { root: "/z", name: "Dün", pinned: false, updated_at: 10 },
          { root: "/a", name: "Sabit", pinned: true, updated_at: 1 },
          { root: "/b", name: "Bugün", pinned: false, updated_at: 20 },
        ]}
      />,
    );

    const projectButtons = screen.getAllByRole("button", { name: /projesini aç/i });
    expect(projectButtons.map((button) => button.textContent)).toEqual(["Sabit", "Bugün", "Dün"]);
  });

  it("yalnız keşfedilmiş geçmiş kaynaklarını önerir", () => {
    render(
      <Sidebar
        availableSources={["claude", "codex"]}
        etkin={null}
        onSec={vi.fn()}
        onYeni={vi.fn()}
        oturumlar={[]}
      />,
    );
    expect(screen.getByRole("button", { name: /claude geçmişi/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /codex geçmişi/i })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /hermes geçmişi/i })).toBeNull();
  });

  it("dar modda metni saklarken erişilebilir adları korur", () => {
    const { container } = render(
      <Sidebar collapsed etkin={null} onSec={vi.fn()} onYeni={vi.fn()} oturumlar={[]} />,
    );
    expect(container.querySelector(".sidebar")?.getAttribute("data-collapsed")).toBe("true");
    expect(screen.getByRole("button", { name: /yeni sohbet/i })).toBeTruthy();
  });

  it("ikon rayında sohbet ve projelerin görünür kimliğini korur", () => {
    const style = document.createElement("style");
    style.dataset.testSidebarStyles = "true";
    style.textContent = sidebarStyles;
    document.head.append(style);
    render(
      <Sidebar
        collapsed
        etkin={null}
        onNavigate={vi.fn()}
        onSec={vi.fn()}
        onYeni={vi.fn()}
        oturumlar={sessions}
        projeler={[{ root: "/fusion", name: "Fusion", pinned: true, updated_at: 1 }]}
      />,
    );

    const session = screen.getByRole("button", { name: "İlk iş" });
    const project = screen.getByRole("button", { name: "Fusion projesini aç" });
    expect(getComputedStyle(session).display).not.toBe("none");
    expect(getComputedStyle(project).display).not.toBe("none");
    expect(getComputedStyle(session.querySelector(".source-icon")!).display).not.toBe("none");
    expect(getComputedStyle(project.querySelector(".sidebar__label")!).display).not.toBe("none");
  });
});

describe("Sidebar — sohbet silme ve projeye gruplama", () => {
  const gruplu = [
    { session_id: "1", source: "fusion", title: "oyun", project: "voltiva" },
    { session_id: "2", source: "claude", title: "site", project: "voltiva" },
    { session_id: "3", source: "fusion", title: "serbest" },
  ];

  it("sohbetleri projesine göre gruplar; projesizler sonda toplanır", () => {
    render(<Sidebar oturumlar={gruplu} etkin="1" onSec={vi.fn()} onYeni={vi.fn()} />);

    expect(screen.getByRole("region", { name: "voltiva" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "Sohbetler" })).toBeTruthy();
  });

  it("geçmişi varsayılan açık gösterir, daraltır ve tercihi saklar", () => {
    const { unmount } = render(<Sidebar oturumlar={gruplu} etkin="1" onSec={vi.fn()} onYeni={vi.fn()} />);
    const toggle = screen.getByRole("button", { name: "Geçmişi daralt" });
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("oyun")).toBeTruthy();
    fireEvent.click(toggle);
    expect(screen.queryByText("oyun")).toBeNull();
    expect(localStorage.getItem("fusion.sidebar.history-open.v1")).toBe("false");
    unmount();

    render(<Sidebar oturumlar={gruplu} etkin="1" onSec={vi.fn()} onYeni={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Geçmişi genişlet" }).getAttribute("aria-expanded")).toBe("false");
  });

  it("çöp kutusu tek tıkta silmeyi başlatır", async () => {
    const sil = vi.fn();
    render(<Sidebar oturumlar={gruplu} etkin="1" onSec={vi.fn()} onSil={sil} onYeni={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "oyun sohbetini sil" }));
    await waitFor(() => expect(sil).toHaveBeenCalledWith("1"));
    expect(screen.queryByRole("button", { name: "Silmekten vazgeç" })).toBeNull();
  });
  it("Fusion sohbetlerinde marka logosu basmaz, içe aktarılanda basar", () => {
    const { container } = render(
      <Sidebar
        oturumlar={[
          { session_id: "a", title: "oyun yaz", source: "fusion", project: "fusion-cli" },
          { session_id: "b", title: "eski sohbet", source: "claude", project: "fusion-cli" },
        ]}
        etkin={null}
        onSec={vi.fn()}
        onYeni={vi.fn()}
      />,
    );

    // Fusion satırı nötr işaret taşır, MARKA LOGOSU değil. Dar kipte başlık
    // gizlendiği için satırın büsbütün boş kalmaması gerekir.
    expect(container.querySelectorAll(".sidebar__session-dot")).toHaveLength(1);
    expect(container.querySelectorAll('.source-icon[data-source="fusion"]')).toHaveLength(0);
    expect(container.querySelectorAll('.source-icon[data-source="claude"]')).toHaveLength(1);
  });
  it("her satirda tek bir isaret sutunu tutar, baslik daralmaz", () => {
    // Başlık bir kez 18 piksellik rozet sütununa düşüp tek harfe kırpılmıştı;
    // işaret sütunu her satırda dolu kaldığı sürece bu tekrarlayamaz.
    const { container } = render(
      <Sidebar
        oturumlar={[{ session_id: "a", title: "oyun yaz", source: "fusion", project: "p" }]}
        etkin={null}
        onSec={vi.fn()}
        onYeni={vi.fn()}
      />,
    );

    const satir = container.querySelector(".sidebar__session");
    expect(satir?.querySelector(".sidebar__session-dot")).toBeTruthy();
    expect(satir?.querySelector(".sidebar__session-title")?.textContent).toBe("oyun yaz");
  });
});


describe("Sidebar yeni düzen", () => {
  const many = Array.from({ length: 7 }, (_, i) => ({ session_id: String(i), source: "fusion", title: `Sohbet ${i}`, project: "Desktop", projectRoot: "/Users/test/Desktop", updated_at: i }));
  it("en yeni beşi gösterir, daha fazla ile kalanları açar", () => {
    render(<Sidebar etkin={null} oturumlar={many} onYeni={vi.fn()} onSec={vi.fn()} />);
    expect(screen.queryByText("Sohbet 0")).toBeNull();
    expect(screen.getByText("Sohbet 6")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Desktop: Daha fazla göster" }));
    expect(screen.getByText("Sohbet 0")).toBeTruthy();
  });
  it("sabitlemeyi yeniden açılışta korur ve eski sohbeti ilk beşe taşır", () => {
    const props = { etkin: null, oturumlar: many, onYeni: vi.fn(), onSec: vi.fn() };
    const view = render(<Sidebar {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Desktop: Daha fazla göster" }));
    fireEvent.click(screen.getByRole("button", { name: "Sohbet 0 sohbetini sabitle" }));
    view.unmount(); render(<Sidebar {...props} />);
    expect(screen.getByRole("button", { name: "Sohbet 0 sohbetini sabitlemekten çıkar" }).getAttribute("aria-pressed")).toBe("true");
  });
  it("oluşturma sayfalarına yönlendirir", () => {
    const navigate = vi.fn();
    render(<Sidebar etkin={null} oturumlar={[]} onYeni={vi.fn()} onSec={vi.fn()} onNavigate={navigate} />);
    fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));
    fireEvent.click(screen.getByRole("button", { name: "Video oluştur" }));
    expect(navigate.mock.calls).toEqual([["image-create"], ["video-create"]]);
  });
});

it("silme hatasını gösterir ve sabitlemeyi yalnız başarılı silmede kaldırır", async () => {
  const remove = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(undefined);
  render(<Sidebar etkin={null} oturumlar={[sessions[0]]} onYeni={vi.fn()} onSec={vi.fn()} onSil={remove} />);
  fireEvent.click(screen.getByRole("button", { name: "İlk iş sohbetini sabitle" }));
  fireEvent.click(screen.getByRole("button", { name: "İlk iş sohbetini sil" }));
  await screen.findByRole("alert");
  expect(JSON.parse(localStorage.getItem("fusion.sidebar.pinned-sessions.v1")!)).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "İlk iş sohbetini sil" }));
  await waitFor(() => expect(JSON.parse(localStorage.getItem("fusion.sidebar.pinned-sessions.v1")!)).toEqual([]));
});

it("StrictMode ve depolama hatasında sabitleme arayüzünü çalışır tutar", () => {
  const write = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
  try {
    render(<StrictMode><Sidebar etkin={null} oturumlar={[sessions[0]]} onYeni={vi.fn()} onSec={vi.fn()} /></StrictMode>);
    fireEvent.click(screen.getByRole("button", { name: "İlk iş sohbetini sabitle" }));
    expect(screen.getByRole("button", { name: "İlk iş sohbetini sabitlemekten çıkar" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("alert").textContent).toContain("kaydedilemedi");
  } finally { write.mockRestore(); }
});

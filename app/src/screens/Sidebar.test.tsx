import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";

const sessions = [
  { session_id: "1", title: "İlk iş", source: "claude", project: "Şeker Oyunu" },
  { session_id: "2", title: "İkinci iş", source: "codex", project: "Kurumsal Site" },
];

afterEach(cleanup);

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
    screen.getByText("Yeni görev").click();
    expect(onYeni).toHaveBeenCalledOnce();
  });

  it("ürünün ana bölümlerini tek navigasyonda gösterir", () => {
    render(<Sidebar oturumlar={[]} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} />);
    expect(screen.getByRole("button", { name: /yeni görev/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /beceriler ve ajanlar/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /dersler/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /kontrol paneli/i })).toBeTruthy();
    expect(screen.getByRole("button", { name: /ayarlar/i })).toBeTruthy();
  });

  it("aramayla oturumları başlık ve kaynak üzerinden filtreler", () => {
    render(<Sidebar oturumlar={sessions} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} />);
    fireEvent.change(screen.getByRole("searchbox", { name: /ara/i }), {
      target: { value: "codex" },
    });
    expect(screen.queryByText("İlk iş")).toBeNull();
    expect(screen.getByText("İkinci iş")).toBeTruthy();
  });

  it("Türkçe proje adıyla arar", () => {
    render(<Sidebar oturumlar={sessions} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} />);
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
    expect(screen.getByText("Sabit projeler")).toBeTruthy();
    expect(screen.getByText("Yakın projeler")).toBeTruthy();
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
    expect(screen.getByRole("button", { name: /yeni görev/i })).toBeTruthy();
  });
});

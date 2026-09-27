import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppHeader } from "./AppHeader";

afterEach(cleanup);

describe("AppHeader", () => {
  it("konuşma ve projeyi gösterir; üst köşede yinelenen çalışma yazısı yoktur", () => {
    render(
      <AppHeader
        inspectorOpen
        onToggleInspector={vi.fn()}
        onToggleSidebar={vi.fn()}
        projectName="fusion-cli"
        sidebarCollapsed={false}
        status="Çalışıyor"
        title="macOS uygulaması"
      />,
    );
    expect(screen.getByRole("heading", { name: "macOS uygulaması" })).toBeTruthy();
    expect(screen.getByText("fusion-cli")).toBeTruthy();
    expect(screen.queryByText("Çalışıyor")).toBeNull();
  });

  it("paylaş düğmesini bağlar ve bağlantı hatasını görünür tutar", () => {
    const onShare = vi.fn();
    render(<AppHeader inspectorOpen={false} onShare={onShare} onToggleInspector={vi.fn()} onToggleSidebar={vi.fn()} sidebarCollapsed={false} status="Bağlantı kesildi" title="Sohbet" />);
    fireEvent.click(screen.getByRole("button", { name: "Sohbeti paylaş" }));
    expect(onShare).toHaveBeenCalledOnce();
    expect(screen.getByRole("alert").textContent).toBe("Bağlantı kesildi");
  });

  it("iki panel düğmesinin açık durumunu erişilebilir biçimde taşır", () => {
    render(
      <AppHeader
        inspectorOpen={false}
        onToggleInspector={vi.fn()}
        onToggleSidebar={vi.fn()}
        sidebarCollapsed
        title="Yeni görev"
      />,
    );
    expect(screen.getByRole("button", { name: /navigasyonu aç/i }).getAttribute("aria-expanded")).toBe(
      "false",
    );
    expect(screen.getByRole("button", { name: /denetçiyi aç/i }).getAttribute("aria-expanded")).toBe(
      "false",
    );
  });

  it("geri/ileri işleyicisi verilmezse gezinme düğmelerini çizmez", () => {
    render(
      <AppHeader
        inspectorOpen
        onToggleInspector={vi.fn()}
        onToggleSidebar={vi.fn()}
        sidebarCollapsed={false}
        title="Sohbet"
      />,
    );
    expect(screen.queryByRole("button", { name: "Geri git" })).toBeNull();
    expect(screen.queryByRole("button", { name: "İleri git" })).toBeNull();
  });

  it("geri/ileri işleyicileri verilince düğmeleri çizer ve yığın durumuna göre etkinleştirir", () => {
    const onNavigateBack = vi.fn();
    const onNavigateForward = vi.fn();
    render(
      <AppHeader
        canNavigateBack
        canNavigateForward={false}
        inspectorOpen
        onNavigateBack={onNavigateBack}
        onNavigateForward={onNavigateForward}
        onToggleInspector={vi.fn()}
        onToggleSidebar={vi.fn()}
        sidebarCollapsed={false}
        title="Sohbet"
      />,
    );
    const backButton = screen.getByRole("button", { name: "Geri git" });
    const forwardButton = screen.getByRole("button", { name: "İleri git" });
    expect(backButton.hasAttribute("disabled")).toBe(false);
    expect(forwardButton.hasAttribute("disabled")).toBe(true);
    fireEvent.click(backButton);
    expect(onNavigateBack).toHaveBeenCalledOnce();
  });

  it("başlık alanının boş kısmı pencereyi sürükletir", () => {
    const { container } = render(
      <AppHeader
        inspectorOpen
        onToggleInspector={vi.fn()}
        onToggleSidebar={vi.fn()}
        sidebarCollapsed={false}
        title="Sohbet"
      />,
    );
    expect(container.querySelector(".app-header__identity")?.hasAttribute("data-tauri-drag-region")).toBe(true);
  });

  it("tema seçicisini BAŞLIKTA çizmez", () => {
    // Tema bir tercihtir ve yeri Ayarlar'dır. Başlıkta durması gereksiz yer
    // kaplıyor ve günlük kullanımda yanlışlıkla değiştirilmesine yol açıyordu.
    render(
      <AppHeader
        inspectorOpen
        onToggleInspector={vi.fn()}
        onToggleSidebar={vi.fn()}
        sidebarCollapsed={false}
        title="Yeni görev"
      />,
    );
    expect(screen.queryByRole("combobox", { name: "Tema" })).toBeNull();
  });
});

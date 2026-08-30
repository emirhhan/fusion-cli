import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Inspector } from "./Inspector";

afterEach(cleanup);

describe("Inspector", () => {
  it("bağlamsal araçları erişilebilir sekmeler olarak sunar", () => {
    render(<Inspector />);
    expect(screen.getByRole("tablist", { name: "Denetçi araçları" })).toBeTruthy();
    expect(screen.getAllByRole("tab")).toHaveLength(7);
    expect(screen.getByRole("tabpanel")).toBeTruthy();
  });

  it("ok tuşlarıyla sekmeler arasında dolaşır", () => {
    render(<Inspector />);
    const files = screen.getByRole("tab", { name: "Dosyalar" });
    files.focus();
    fireEvent.keyDown(files, { key: "ArrowRight" });
    expect(screen.getByRole("tab", { name: "Değişiklikler" }).getAttribute("aria-selected")).toBe(
      "true",
    );
  });

  it("boş, yükleniyor ve hata durumlarını dürüst metinle gösterir", () => {
    const { rerender } = render(<Inspector />);
    expect(screen.getByText(/henüz bir proje seçilmedi/i)).toBeTruthy();
    rerender(<Inspector status="loading" />);
    expect(screen.getByText("Yükleniyor…")).toBeTruthy();
    rerender(<Inspector errorMessage="Proje okunamadı" status="error" />);
    expect(screen.getByRole("alert").textContent).toContain("Proje okunamadı");
  });

  it("320–680 piksel arasında klavyeyle yeniden boyutlandırılır", () => {
    const onWidthChange = vi.fn();
    render(<Inspector onWidthChange={onWidthChange} width={420} />);
    const separator = screen.getByRole("separator", { name: "Çalışma panelini yeniden boyutlandır" });
    expect(separator.getAttribute("aria-valuenow")).toBe("420");
    fireEvent.keyDown(separator, { key: "ArrowLeft" });
    expect(onWidthChange).toHaveBeenLastCalledWith(404);
    fireEvent.keyDown(separator, { key: "Home" });
    expect(onWidthChange).toHaveBeenLastCalledWith(320);
    fireEvent.keyDown(separator, { key: "End" });
    expect(onWidthChange).toHaveBeenLastCalledWith(680);
  });

  it("ayırıcı sürüklendiğinde sağ panel genişliğini canlı günceller", () => {
    const onWidthChange = vi.fn();
    render(<Inspector onWidthChange={onWidthChange} width={420} />);
    const separator = screen.getByRole("separator", { name: "Çalışma panelini yeniden boyutlandır" });
    fireEvent.pointerDown(separator, { button: 0, clientX: 800 });
    fireEvent.pointerMove(window, { clientX: 768 });
    expect(onWidthChange).toHaveBeenLastCalledWith(452);
    fireEvent.pointerUp(window);
  });

  it("sürükleme dinleyicilerini unmount sırasında temizler", () => {
    const onWidthChange = vi.fn();
    const view = render(<Inspector onWidthChange={onWidthChange} width={420} />);
    fireEvent.pointerDown(
      screen.getByRole("separator", { name: "Çalışma panelini yeniden boyutlandır" }),
      { button: 0, clientX: 800 },
    );
    view.unmount();
    fireEvent.pointerMove(window, { clientX: 700 });
    expect(onWidthChange).not.toHaveBeenCalled();
  });

  it("daraltıldığında araç şeridini korur ve yeniden açılabilir", () => {
    const onCollapsedChange = vi.fn();
    const { container } = render(<Inspector collapsed onCollapsedChange={onCollapsedChange} />);
    expect(container.querySelector(".inspector")?.getAttribute("data-collapsed")).toBe("true");
    expect(screen.getByRole("tablist", { name: "Denetçi araçları" })).toBeTruthy();
    expect(screen.queryByRole("tabpanel")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Çalışma panelini genişlet" }));
    expect(onCollapsedChange).toHaveBeenCalledWith(false);
  });

  it("etkin sekmeyi kontrollü sözleşmeyle bildirir", () => {
    const onActiveTabChange = vi.fn();
    render(<Inspector activeTab="terminal" onActiveTabChange={onActiveTabChange} />);
    expect(screen.getByRole("tab", { name: "Terminal" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.click(screen.getByRole("tab", { name: "Önizleme" }));
    expect(onActiveTabChange).toHaveBeenCalledWith("preview");
  });

  it("istenen sekmeyi yalnız bir kez uygular ve kullanıcı seçimini kilitlemez", () => {
    const onActiveTabChange = vi.fn();
    const view = render(
      <Inspector activeTab="files" onActiveTabChange={onActiveTabChange} requestedTab="files" />,
    );
    expect(onActiveTabChange).toHaveBeenCalledWith("files");
    onActiveTabChange.mockClear();
    view.rerender(
      <Inspector activeTab="terminal" onActiveTabChange={onActiveTabChange} requestedTab="files" />,
    );
    expect(screen.getByRole("tab", { name: "Terminal" }).getAttribute("aria-selected")).toBe("true");
    expect(onActiveTabChange).not.toHaveBeenCalled();
  });

  it("daraltılmış araç şeridinde olmayan panellere aria-controls vermez", () => {
    render(<Inspector collapsed />);
    expect(screen.getByRole("tab", { name: "Dosyalar" }).hasAttribute("aria-controls")).toBe(false);
  });

  it("geniş görünümde yalnız bağlı aktif sekmeye aria-controls verir", () => {
    render(<Inspector activeTab="files" />);
    expect(screen.getByRole("tab", { name: "Dosyalar" }).getAttribute("aria-controls")).toBe("inspector-panel-files");
    expect(screen.getByRole("tab", { name: "Terminal" }).hasAttribute("aria-controls")).toBe(false);
  });
});

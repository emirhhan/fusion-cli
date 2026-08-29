import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppHeader } from "./AppHeader";

afterEach(cleanup);

describe("AppHeader", () => {
  it("konuşma, proje ve çalışma durumunu açıkça gösterir", () => {
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
    expect(screen.getByText("Çalışıyor")).toBeTruthy();
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

  it("tema tercihini erişilebilir seçiciden bildirir", () => {
    const onThemeChange = vi.fn();
    render(
      <AppHeader
        inspectorOpen
        onThemeChange={onThemeChange}
        onToggleInspector={vi.fn()}
        onToggleSidebar={vi.fn()}
        sidebarCollapsed={false}
        themePreference="system"
        title="Yeni görev"
      />,
    );
    fireEvent.change(screen.getByRole("combobox", { name: "Tema" }), {
      target: { value: "dark" },
    });
    expect(onThemeChange).toHaveBeenCalledWith("dark");
  });
});

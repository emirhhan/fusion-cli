import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MainSurface } from "../sections/MainSurface";
import { MAIN_SECTIONS, MainRail } from "./MainRail";
import { Shell } from "./Shell";

afterEach(cleanup);

describe("MainRail", () => {
  it("bölümleri kullanıcının belirlediği sırayla gösterir", () => {
    render(<MainRail active="home" onSelect={vi.fn()} />);
    const labels = screen.getAllByRole("button").map((button) => button.textContent);
    expect(labels).toEqual(["Home", "Zamanlananlar", "Kitaplık", "Görsel ve video üretimi", "Kits"]);
    expect(MAIN_SECTIONS.map((item) => item.id)).toEqual(["home", "scheduled", "library", "media", "kits"]);
  });

  it("etkin bölümü işaretler ve seçimi bildirir", () => {
    const select = vi.fn();
    render(<MainRail active="library" onSelect={select} />);
    expect(screen.getByRole("button", { name: "Kitaplık" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("button", { name: "Home" }).getAttribute("aria-current")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Kits" }));
    expect(select).toHaveBeenCalledWith("kits");
  });
});

describe("Shell ana menü yuvası", () => {
  it("ray verilmezse kabuk eskisi gibi tek başına çizilir", () => {
    const { container } = render(<Shell content="içerik" sidebar="kenar" />);
    expect(container.querySelector(".app-frame")).toBeNull();
    expect(container.firstElementChild?.className).toBe("app-shell");
  });

  it("bölüm yüzeyi açıkken kabuğu gizler ama DOM'da tutar", () => {
    const { container, rerender } = render(
      <Shell content="sohbet" rail={<nav>ray</nav>} sidebar="kenar" surface="bölüm" surfaceActive />,
    );
    expect(container.querySelector(".app-shell")?.hasAttribute("hidden")).toBe(true);
    expect(container.querySelector(".app-frame__surface")?.hasAttribute("hidden")).toBe(false);
    expect(screen.getByText("sohbet")).toBeTruthy();
    rerender(<Shell content="sohbet" rail={<nav>ray</nav>} sidebar="kenar" surface="bölüm" />);
    expect(container.querySelector(".app-shell")?.hasAttribute("hidden")).toBe(false);
    expect(container.querySelector(".app-frame__surface")?.hasAttribute("hidden")).toBe(true);
  });
});

describe("MainSurface", () => {
  const panes = { scheduled: <p>zamanlanan</p>, library: <p>kitaplık</p>, kits: <p>kits</p> };

  it("hiç açılmayan bölümü kurmaz, açılanı menü geçişinde korur", () => {
    const { rerender } = render(<MainSurface {...panes} section={null} />);
    expect(screen.queryByText("kits")).toBeNull();
    rerender(<MainSurface {...panes} section="kits" />);
    expect(screen.getByText("kits").closest("section")?.hasAttribute("hidden")).toBe(false);
    rerender(<MainSurface {...panes} section="library" />);
    expect(screen.getByText("kits").closest("section")?.hasAttribute("hidden")).toBe(true);
    expect(screen.getByText("kitaplık").closest("section")?.hasAttribute("hidden")).toBe(false);
    expect(screen.queryByText("zamanlanan")).toBeNull();
  });
});

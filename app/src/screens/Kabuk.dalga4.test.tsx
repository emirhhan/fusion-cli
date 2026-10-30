import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppHeader, BAGLANTI_KESILDI_DURUMU } from "./AppHeader";
import { Inspector } from "./Inspector";
import { MainRail } from "./MainRail";
import { RuntimeSetup } from "./RuntimeSetup";
import { ProjectPicker } from "./ProjectPicker";
import { useStickToBottom } from "./useStickToBottom";
import { renderHook } from "@testing-library/react";

afterEach(cleanup);

describe("kabuk — dalga 4 P2/P3", () => {
  it("başlık bağlantı kesildi uyarısını paylaşılan sabitle gösterir (U1-61)", () => {
    render(<AppHeader inspectorOpen={false} onToggleInspector={vi.fn()} onToggleSidebar={vi.fn()} sidebarCollapsed={false} status={BAGLANTI_KESILDI_DURUMU} title="x" />);
    expect(screen.getByRole("alert").textContent).toBe("Bağlantı kesildi");
  });

  it("bilinmeyen etkin sekme panelin çökmesine yol açmaz, ilk sekmeye döner (U1-62)", () => {
    // @ts-expect-error kaldırılmış sekme kimliği saklı veriden gelebilir
    const { container } = render(<Inspector activeTab="kaldirilmis" />);
    expect(container.querySelector('[role="tabpanel"]')).not.toBeNull();
    expect(screen.getAllByRole("tab").filter((tab) => tab.getAttribute("aria-selected") === "true")).toHaveLength(1);
  });

  it("yeniden boyutlandırma imleci tutamaçta yakalar (U1-63)", () => {
    render(<Inspector onWidthChange={vi.fn()} />);
    const tutamac = screen.getByRole("separator");
    const capture = vi.fn();
    (tutamac as unknown as { setPointerCapture: unknown }).setPointerCapture = capture;
    fireEvent.pointerDown(tutamac, { button: 0, pointerId: 7, clientX: 100 });
    expect(capture).toHaveBeenCalledWith(7);
  });

  it("ana menü etiketi ekran okuyucuya iki kez okunmaz (U1-65)", () => {
    const { container } = render(<MainRail active="home" onSelect={vi.fn()} />);
    expect(container.querySelector("[aria-describedby]")).toBeNull();
    expect(container.querySelector('[role="tooltip"]')?.getAttribute("aria-hidden")).toBe("true");
  });

  it("başlatma hatasında ileti yalnız bir kez görünür (U1-66)", () => {
    render(<RuntimeSetup state="hata" progress={0} message="Disk dolu" version="1.2" onRepair={vi.fn()} />);
    expect(screen.getAllByText("Disk dolu")).toHaveLength(1);
  });

  it("proje seçici hatası bir sonraki açılışta kalmaz (U1-67)", async () => {
    const onSelect = vi.fn().mockRejectedValue(new Error("x"));
    render(<ProjectPicker root="/a" projects={[{ root: "/b", name: "B", updated_at: 1 } as never]} onSelect={onSelect} onNew={vi.fn()} onSettings={vi.fn()} />);
    const tetik = screen.getByRole("button", { name: /Proje seç/ });
    fireEvent.click(tetik);
    fireEvent.click(screen.getByTitle("/b"));
    expect((await screen.findByRole("alert")).textContent).toContain("açılamadı");
    fireEvent.click(tetik);
    fireEvent.click(tetik);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("scrollTo 'instant' değerinde TypeError atsa da alta iner (U1-69)", () => {
    const kutu = document.createElement("div");
    Object.defineProperty(kutu, "scrollHeight", { value: 500, configurable: true });
    kutu.scrollTo = (() => { throw new TypeError("bad behavior"); }) as never;
    const kutuRef = { current: kutu };
    const icerikRef = createRef<HTMLElement>();
    const { result } = renderHook(() => useStickToBottom(kutuRef, icerikRef, 1, false));
    result.current.enAltaIn();
    expect(kutu.scrollTop).toBe(500);
  });
});

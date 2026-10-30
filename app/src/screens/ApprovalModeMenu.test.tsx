import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_DEADLINES_MS } from "../protocol/client";
import { ApprovalModeMenu } from "./ApprovalModeMenu";
import { ContextGauge } from "./ContextGauge";

afterEach(cleanup);

describe("ApprovalModeMenu — odak yönetimi (U1-49)", () => {
  const ac = () => {
    render(<ApprovalModeMenu mode="auto" onChange={vi.fn()} />);
    const tetik = screen.getByRole("button", { name: /İzin modu: Otomatik/ });
    fireEvent.click(tetik);
    return tetik;
  };

  it("Escape menüyü kapatır ve odağı tetikleyiciye döndürür", () => {
    const tetik = ac();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(tetik);
  });

  it("Tab menüyü açık bırakmaz", () => {
    const tetik = ac();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Tab" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.activeElement).toBe(tetik);
  });

  it("seçim sonrası odak tetikleyicide kalır", () => {
    const tetik = ac();
    fireEvent.click(screen.getByRole("menuitemradio", { name: /Manuel/ }));
    expect(document.activeElement).toBe(tetik);
  });

  it("Home ve End ilk ve son maddeye odaklanır", () => {
    ac();
    const menu = screen.getByRole("menu");
    fireEvent.keyDown(menu, { key: "End" });
    expect(document.activeElement?.textContent).toContain("İzinleri atla");
    fireEvent.keyDown(menu, { key: "Home" });
    expect(document.activeElement?.textContent).toContain("Otomatik");
  });
});

describe("ContextGauge — bozuk ölçü (U1-46)", () => {
  const olcu = (yuzde: number) => ({ kullanilan: 1, sinir: 2, yuzde });
  it("100'ü aşan yüzde 100'e sıkışır, negatif etiket çıkmaz", () => {
    render(<ContextGauge olcu={olcu(140)} />);
    expect(screen.getByRole("meter").getAttribute("aria-valuenow")).toBe("100");
  });
  it("sayı olmayan yüzde hiçbir şey çizmez", () => {
    const { container } = render(<ContextGauge olcu={olcu(Number.NaN)} />);
    expect(container.firstChild).toBeNull();
  });
  it("Escape kartı kapatır ve odağı halkaya döndürür (U1-47)", () => {
    render(<ContextGauge olcu={olcu(50)} />);
    const halka = screen.getByRole("meter");
    fireEvent.click(halka);
    expect(screen.getByRole("dialog")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(halka);
  });
});

describe("model seçici istekleri (U1-41)", () => {
  it("model.katalog ve kontrol.durum varsayılan son süre taşır", () => {
    expect(DEFAULT_DEADLINES_MS["model.katalog"]).toBeGreaterThan(0);
    expect(DEFAULT_DEADLINES_MS["kontrol.durum"]).toBeGreaterThan(0);
  });
});

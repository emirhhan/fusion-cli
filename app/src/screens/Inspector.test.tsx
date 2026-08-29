import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
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
});

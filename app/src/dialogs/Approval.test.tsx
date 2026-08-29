import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Approval } from "./Approval";

const temel = {
  tur: "onay" as const,
  arac: "write_file",
  argumanlar: { path: "a.txt" },
  tehlike: null,
  secenekler: [
    { deger: "once", etiket: "Bir kez izin ver" },
    { deger: "session", etiket: "Oturum boyunca izin ver" },
    { deger: "deny", etiket: "Reddet" },
  ],
};

afterEach(cleanup);

describe("Approval", () => {
  it("hangi aracın ve hangi argümanların onaylandığını gösterir", () => {
    render(<Approval soru={temel} onCevap={vi.fn()} />);
    expect(screen.getByText(/write_file/)).toBeTruthy();
    expect(screen.getByText(/a\.txt/)).toBeTruthy();
  });

  it("gelen seçenekleri olduğu gibi çizer", () => {
    render(<Approval soru={temel} onCevap={vi.fn()} />);
    expect(screen.getByText("Oturum boyunca izin ver")).toBeTruthy();
  });

  it("çekirdeğin çıkardığı oturum seçeneğini yeniden eklemez", () => {
    const yikici = {
      ...temel,
      tehlike: "dosya siler",
      secenekler: temel.secenekler.filter((secenek) => secenek.deger !== "session"),
    };
    render(<Approval soru={yikici} onCevap={vi.fn()} />);
    expect(screen.queryByText("Oturum boyunca izin ver")).toBeNull();
    expect(screen.getByText(/dosya siler/)).toBeTruthy();
  });

  it("seçim yapılınca değeri bildirir", () => {
    const onCevap = vi.fn();
    render(<Approval soru={temel} onCevap={onCevap} />);
    screen.getByText("Reddet").click();
    expect(onCevap).toHaveBeenCalledWith({ secim: "deny" });
  });

  it("açıldığında diyaloğa odaklanır ve güvenli reddi Escape ile seçer", () => {
    const onCevap = vi.fn();
    render(<Approval soru={temel} onCevap={onCevap} />);
    expect(document.activeElement).toBe(screen.getByRole("dialog"));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onCevap).toHaveBeenCalledWith({ secim: "deny" });
  });

  it("önerilen seçeneği semantik olarak işaretler", () => {
    render(<Approval soru={{ ...temel, onerilen: "once" }} onCevap={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Bir kez izin ver" }).getAttribute("data-recommended")).toBe(
      "true",
    );
  });
});

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ActivityLine, ToolTrail } from "./ActivityLine";
import { PreviewCard } from "./PreviewCard";
import { httpAdresiMi } from "./safeUrl";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ActivityLine — dalga 4 P2", () => {
  it("canlı satır 'düşünüyor' adımıysa biten araç izden düşmez (U1-30)", () => {
    render(<ActivityLine compact adimlar={[
      { metin: "main.py okundu", arac: "read_file", durum: "ok" },
      { metin: "sıradakini düşünüyor", basladi: true },
    ]} />);
    expect(screen.getByText("main.py okundu")).toBeTruthy();
  });

  it("araç sonucu glifi ekran okuyucuya sözlü sonuç verir (U1-31)", () => {
    render(<ToolTrail adimlar={[
      { metin: "Komut", arac: "run_shell", durum: "failed" },
      { metin: "Okuma", arac: "read_file", durum: "ok" },
    ]} />);
    expect(screen.getByRole("img", { name: "başarısız" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "başarılı" })).toBeTruthy();
  });

  it("kaynak bağlantısı yalnız http(s) ise tıklanabilir olur (U1-38)", () => {
    render(<ActivityLine aktif={false} showSteps adimlar={[
      { metin: "güvenli", kaynak: "https://ornek.com/a" },
      { metin: "tehlikeli", kaynak: "javascript:alert(1)" },
      { metin: "yerel", kaynak: "file:///etc/passwd" },
      { metin: "Tur bitti", sonuc: "completed" },
    ]} />);
    fireEvent.click(screen.getByText(/adım · detaylar/));
    expect(screen.getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(["https://ornek.com/a"]);
    expect(screen.getByText("javascript:alert(1)")).toBeTruthy();
  });
});

describe("PreviewCard — dalga 4 (U1-39)", () => {
  it("http(s) dışı adres hiçbir yerde açılmaz", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    render(<PreviewCard url="javascript:alert(1)" />);
    fireEvent.click(screen.getByRole("button", { name: "Tarayıcıda aç" }));
    await new Promise((r) => setTimeout(r, 20));
    expect(open).not.toHaveBeenCalled();
  });

  it("httpAdresiMi yalnız http ve https kabul eder", () => {
    expect(httpAdresiMi("http://localhost:3000")).toBe(true);
    expect(httpAdresiMi("https://a.b/c?d=1")).toBe(true);
    for (const kotu of ["javascript:alert(1)", "file:///x", "data:text/html,<b>", "ornek.com", "", undefined]) {
      expect(httpAdresiMi(kotu)).toBe(false);
    }
  });
});

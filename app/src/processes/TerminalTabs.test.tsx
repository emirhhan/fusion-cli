import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProcessController } from "./useProcesses";
import { stripAnsi, TerminalTabs } from "./TerminalTabs";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function controller(overrides: Partial<ProcessController> = {}): ProcessController {
  return {
    busy: false,
    error: null,
    processes: [
      {
        baslangic: 1,
        cikis_kodu: null,
        cikti: "\u001b]0;gizli terminal başlığı\u0007\u009d0;c1 başlığı\u0007\u001b[32mdev sunucusu hazır\u001b[0m\u001b]0;yarım başlık",
        cwd: "/Projects/fusion-cli",
        durum: "calisiyor",
        komut: "npm run dev",
        pid: 100,
        surec_id: "dev",
      },
      {
        baslangic: 2,
        cikis_kodu: 0,
        cikti: "299 tests passed",
        cwd: "/Projects/fusion-cli/app",
        durum: "bitti",
        komut: "npm test",
        pid: 101,
        surec_id: "tests",
      },
    ],
    outputStreams: {},
    refresh: vi.fn(async () => undefined),
    start: vi.fn(async () => true),
    stop: vi.fn(async () => undefined),
    ...overrides,
  } as ProcessController;
}

describe("TerminalTabs", () => {
  it("süreçleri kayıpsız sekmeler olarak seçer ve ANSI kodlarını çizmez", () => {
    render(<TerminalTabs controller={controller()} />);
    expect(screen.getByText("299 tests passed")).toBeTruthy();
    const tests = screen.getByRole("tab", { name: "npm test terminali" });
    fireEvent.keyDown(tests, { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "npm run dev terminali" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("dev sunucusu hazır")).toBeTruthy();
    expect(document.body.textContent).not.toContain("\u001b[32m");
    expect(document.body.textContent).not.toContain("gizli terminal başlığı");
    expect(document.body.textContent).not.toContain("c1 başlığı");
    expect(document.body.textContent).not.toContain("yarım başlık");
  });

  it("başlatma sonrası gelen yeni süreç sekmesini otomatik etkinleştirir", () => {
    const initial = controller({ processes: [] });
    const view = render(<TerminalTabs controller={initial} />);
    const next = controller({ processes: [controller().processes[0]] });
    view.rerender(<TerminalTabs controller={next} />);
    expect(screen.getByRole("tab", { name: "npm run dev terminali" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByText("dev sunucusu hazır")).toBeTruthy();
  });

  it("çalışan süreci durdurur, bitmiş sekmeyi yalnız görünümden kapatır", () => {
    const value = controller();
    render(<TerminalTabs controller={value} />);
    fireEvent.click(screen.getByRole("tab", { name: "npm run dev terminali" }));
    fireEvent.click(screen.getByRole("button", { name: "Süreci durdur" }));
    expect(value.stop).toHaveBeenCalledWith("dev");

    fireEvent.click(screen.getByRole("tab", { name: "npm test terminali" }));
    fireEvent.click(screen.getByRole("button", { name: "Terminal sekmesini kapat" }));
    expect(screen.queryByRole("tab", { name: "npm test terminali" })).toBeNull();
    expect(value.stop).toHaveBeenCalledTimes(1);
  });

  it("artı düğmesiyle komut composer'ını açar ve mevcut start sözleşmesini kullanır", async () => {
    const value = controller({ processes: [] });
    render(<TerminalTabs controller={value} />);
    fireEvent.click(screen.getByRole("button", { name: "Yeni terminal" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Terminal komutu" }), {
      target: { value: "npm run build" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Çalıştır" }));
    await waitFor(() => expect(value.start).toHaveBeenCalledWith("npm run build"));
  });

  it("çıktıyı temizler, panoya kopyalar ve yeni satırda sona kaydırır", async () => {
    Object.defineProperty(HTMLElement.prototype, "scrollHeight", {
      configurable: true,
      get: () => 640,
    });
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(<TerminalTabs controller={controller()} />);
    const output = screen.getByRole("log", { name: "Terminal çıktısı" });
    expect(output.scrollTop).toBe(640);
    fireEvent.click(screen.getByRole("button", { name: "Çıktıyı kopyala" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("299 tests passed"));
    fireEvent.click(screen.getByRole("button", { name: "Çıktıyı temizle" }));
    expect(screen.queryByText("299 tests passed")).toBeNull();
  });

  it("dönen backend tamponunda temizleme sonrasındaki yeni son eki gösterir", () => {
    const process = { ...controller().processes[0], cikti: "abcdef" };
    const view = render(<TerminalTabs controller={controller({ processes: [process] })} />);
    fireEvent.click(screen.getByRole("button", { name: "Çıktıyı temizle" }));
    view.rerender(
      <TerminalTabs controller={controller({ processes: [{ ...process, cikti: "cdefgh" }] })} />,
    );
    expect(screen.getByText("gh")).toBeTruthy();
  });

  it("aynı içerikli dönen tamponda yeni olay parçalarını temizleme sonrasında gösterir", () => {
    const repeated = "x".repeat(256 * 1024);
    const process = { ...controller().processes[0], cikti: repeated };
    const view = render(<TerminalTabs controller={controller({ processes: [process] })} />);
    fireEvent.click(screen.getByRole("button", { name: "Çıktıyı temizle" }));

    view.rerender(<TerminalTabs controller={controller({
      outputStreams: { dev: { text: "x".repeat(4096), total: 4096 } },
      processes: [{ ...process, cikti: repeated }],
    })} />);

    expect(screen.getByRole("log", { name: "Terminal çıktısı" }).textContent).toBe("x".repeat(4096));
  });

  it("C1 OSC dizisini C1 ST sonlandırıcısında kesip sonraki metni korur", () => {
    expect(stripAnsi("before\u009d0;başlık\u009cafter")).toBe("beforeafter");
  });

  it("başlatma başarısızsa komutu korur; bitmiş süreci cwd ile yeniden çalıştırır", async () => {
    const failed = controller({ processes: [], start: vi.fn(async () => false) });
    const view = render(<TerminalTabs controller={failed} />);
    const input = screen.getByRole("textbox", { name: "Terminal komutu" });
    fireEvent.change(input, { target: { value: "npm run broken" } });
    fireEvent.click(screen.getByRole("button", { name: "Çalıştır" }));
    await waitFor(() => expect(failed.start).toHaveBeenCalled());
    expect((screen.getByRole("textbox", { name: "Terminal komutu" }) as HTMLInputElement).value).toBe("npm run broken");

    const completed = controller();
    view.rerender(<TerminalTabs controller={completed} />);
    fireEvent.click(screen.getByRole("button", { name: "Yeniden çalıştır" }));
    expect(completed.start).toHaveBeenCalledWith("npm test", "/Projects/fusion-cli/app");
  });
});

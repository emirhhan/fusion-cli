import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";

afterEach(cleanup);

describe("Composer", () => {
  it("Enter ile gönderir, boş girdiyi göndermez", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
    const textbox = screen.getByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "  bir oyun yap  " } });
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("bir oyun yap");
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("Shift+Enter ile yeni satıra izin verir", () => {
    const onSend = vi.fn();
    render(<Composer onSend={onSend} />);
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Mesaj" }), {
      key: "Enter",
      shiftKey: true,
    });
    expect(onSend).not.toHaveBeenCalled();
  });

  it("çalışan görevde gönder yerine durdur eylemi sunar", () => {
    const onStop = vi.fn();
    render(<Composer onSend={vi.fn()} onStop={onStop} running />);
    screen.getByRole("button", { name: "Durdur" }).click();
    expect(onStop).toHaveBeenCalledOnce();
  });

  it("komut ve ek eylemlerini klavyeyle erişilebilir sunar", () => {
    const onCommand = vi.fn();
    const onAttach = vi.fn();
    render(<Composer onAttach={onAttach} onCommand={onCommand} onSend={vi.fn()} />);
    screen.getByRole("button", { name: "Dosya veya klasör ekle" }).click();
    screen.getByRole("button", { name: "Komutlar" }).click();
    expect(onAttach).toHaveBeenCalledOnce();
    expect(onCommand).toHaveBeenCalledOnce();
  });
});

describe("Composer — çalışma kipi", () => {
  it("sohbet ve kod arasında geçiş yapar; varsayılan sohbettir", () => {
    const secilen: string[] = [];
    render(<Composer onModeChange={(m) => secilen.push(m)} onSend={() => undefined} />);

    const sohbet = screen.getByRole("button", { name: "Sohbet" });
    const kod = screen.getByRole("button", { name: "Kod" });
    expect(sohbet.getAttribute("aria-pressed")).toBe("true");
    expect(kod.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(kod);
    expect(secilen).toEqual(["kod"]);
  });

  it("kip değiştirici verilmediğinde hiç çizilmez", () => {
    render(<Composer onSend={() => undefined} />);
    expect(screen.queryByRole("group", { name: "Çalışma kipi" })).toBeNull();
  });
});

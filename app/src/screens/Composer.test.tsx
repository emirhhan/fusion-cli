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

  it("ek eylemini klavyeyle erişilebilir sunar ve ayrı slash düğmesi çizmez", () => {
    const onAttach = vi.fn();
    render(<Composer onAttach={onAttach} onSend={vi.fn()} />);
    screen.getByRole("button", { name: "Dosya veya klasör ekle" }).click();
    expect(onAttach).toHaveBeenCalledOnce();
    expect(screen.queryByRole("button", { name: "Komutlar" })).toBeNull();
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

  it("Shift+Tab ile kipi değiştirir, normal Tab dolaşımını engellemez", () => {
    const onModeChange = vi.fn();
    render(<Composer mode="sohbet" onModeChange={onModeChange} onSend={vi.fn()} />);
    const textbox = screen.getByRole("textbox", { name: "Mesaj" });

    expect(fireEvent.keyDown(textbox, { key: "Tab", shiftKey: true })).toBe(false);
    expect(onModeChange).toHaveBeenCalledWith("kod");

    expect(fireEvent.keyDown(textbox, { key: "Tab" })).toBe(true);
  });
});

describe("Composer — slash paleti ve ekler", () => {
  const commands = [
    { ad: "model", aciklama: "Modeli değiştir", grup: "Model", kullanim: "[alt-komut]", destekleniyor: true },
    { ad: "mode", aciklama: "Profili değiştir", grup: "Model", kullanim: "[profil]", destekleniyor: true },
    { ad: "mcp github", aciklama: "GitHub MCP sunucusu", grup: "MCP", kullanim: "", destekleniyor: true },
  ];

  it("/m yazınca eşleşmeleri gösterir; tıklama komutu inputa taşır", () => {
    render(<Composer commands={commands} onSend={vi.fn()} />);
    const textbox = screen.getByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "/m" } });

    expect(screen.getByRole("listbox", { name: "Komut önerileri" })).toBeTruthy();
    fireEvent.click(screen.getByRole("option", { name: /GitHub MCP sunucusu/i }));
    expect(textbox).toHaveProperty("value", "/mcp github");
    expect(screen.queryByRole("button", { name: "Komutlar" })).toBeNull();
  });

  it("tam komutta Enter komutu çalıştırır", () => {
    const onSend = vi.fn();
    render(<Composer commands={commands} onSend={onSend} />);
    const textbox = screen.getByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "/mcp github" } });
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("/mcp github");
  });

  it("ekleri gösterir, kaldırır ve sürüklenen dosyayı bildirir", () => {
    const onRemove = vi.fn();
    const onDropFiles = vi.fn();
    const { container } = render(
      <Composer
        attachments={[{ path: "/tmp/ornek.png", name: "ornek.png", kind: "image" }]}
        onDropFiles={onDropFiles}
        onRemoveAttachment={onRemove}
        onSend={vi.fn()}
      />,
    );
    expect(screen.getByText("ornek.png")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "ornek.png ekini kaldır" }));
    expect(onRemove).toHaveBeenCalledWith("/tmp/ornek.png");

    const file = new File(["x"], "suruklenen.txt", { type: "text/plain" });
    fireEvent.drop(container.querySelector(".composer")!, { dataTransfer: { files: [file] } });
    expect(onDropFiles).toHaveBeenCalledWith([file]);
  });
});

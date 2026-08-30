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

  it("her kip ne yaptığını anlatır ve etkin kip gruptan okunur", () => {
    // Kullanıcı iki düz düğmeyi "kırılgan" buldu: hangi kipin ne yaptığı
    // yazmıyordu ve seçili olan yeterince belli değildi.
    render(<Composer mode="kod" onModeChange={() => undefined} onSend={() => undefined} />);
    const grup = screen.getByRole("group", { name: "Çalışma kipi" });

    expect(grup.getAttribute("data-mode")).toBe("kod");
    expect(screen.getByRole("button", { name: "Sohbet" }).getAttribute("title")).toMatch(/tarama/i);
    expect(screen.getByRole("button", { name: "Kod" }).getAttribute("title")).toMatch(/proje/i);
  });

  it("kip değişimi sürerken düğmeler kilitlenir", () => {
    const onModeChange = vi.fn();
    render(<Composer modeBusy mode="sohbet" onModeChange={onModeChange} onSend={() => undefined} />);
    const kod = screen.getByRole("button", { name: "Kod" }) as HTMLButtonElement;

    expect(kod.disabled).toBe(true);
    fireEvent.click(kod);
    expect(onModeChange).not.toHaveBeenCalled();
  });

  it("kip değiştirici verilmediğinde hiç çizilmez", () => {
    render(<Composer onSend={() => undefined} />);
    expect(screen.queryByRole("group", { name: "Çalışma kipi" })).toBeNull();
  });

  it("Shift+Tab İZİN modunu döndürür, normal Tab dolaşımını engellemez", () => {
    // Kullanıcı terminaldeki davranışı bekliyor: Shift+Tab izin modunu döndürür.
    // Çalışma kipi (Sohbet/Kod) ayrı düğmelerdedir; ikisini aynı tuşa bindirmek
    // alışkanlığı bozuyordu.
    const onApprovalChange = vi.fn();
    render(<Composer approval="auto" onApprovalChange={onApprovalChange} onSend={vi.fn()} />);
    const textbox = screen.getByRole("textbox", { name: "Mesaj" });

    expect(fireEvent.keyDown(textbox, { key: "Tab", shiftKey: true })).toBe(false);
    expect(onApprovalChange).toHaveBeenCalledWith("plan");

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

describe("Composer — izin modu", () => {
  it("seçili izin modunu gösterir; sabit metin basmaz", () => {
    render(<Composer approval="security" onSend={() => undefined} />);
    expect(screen.getByText(/Güvenli/i)).toBeTruthy();
    expect(screen.queryByText("Agent · Otomatik")).toBeNull();
  });

  it("Shift+Tab izin modunu sırayla değiştirir", () => {
    const secilen: string[] = [];
    render(
      <Composer approval="auto" onApprovalChange={(m) => secilen.push(m)} onSend={() => undefined} />,
    );
    const kutu = screen.getByLabelText("Mesaj");

    fireEvent.keyDown(kutu, { key: "Tab", shiftKey: true });
    expect(secilen).toEqual(["plan"]);
  });

  it("tıklayarak da mod değiştirilebilir", () => {
    const secilen: string[] = [];
    render(
      <Composer approval="plan" onApprovalChange={(m) => secilen.push(m)} onSend={() => undefined} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Yalnız plan/ }));
    expect(secilen).toEqual(["security"]);
  });
});

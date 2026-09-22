import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Composer, maliyetRozetMetni } from "./Composer";

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

  it("kalan bağlamı hem boşta hem iş sürerken mesaj kutusunun yanında gösterir", () => {
    const context = { kullanilan: 20000, sinir: 24000, yuzde: 83 };
    const { rerender } = render(<Composer context={context} onSend={vi.fn()} />);
    expect(screen.getByRole("meter").textContent).toBe("Bağlam %17 kaldı");
    rerender(<Composer context={context} onSend={vi.fn()} running />);
    expect(screen.getByRole("meter").getAttribute("aria-valuenow")).toBe("83");
  });

  it("ölçü yokken bağlam göstergesi çizmez", () => {
    render(<Composer onSend={vi.fn()} />);
    expect(screen.queryByRole("meter")).toBeNull();
  });

  it("maliyet yokken ya da sıfırken rozet çizmez", () => {
    const { rerender } = render(<Composer onSend={vi.fn()} />);
    expect(screen.queryByText(/^\$/)).toBeNull();
    rerender(<Composer costUsd={0} onSend={vi.fn()} />);
    expect(screen.queryByText(/^\$/)).toBeNull();
  });

  it("maliyet varsa hem boşta hem iş sürerken rozet gösterir", () => {
    const { rerender } = render(<Composer costUsd={0.12} onSend={vi.fn()} />);
    expect(screen.getByText("$0.12")).toBeTruthy();
    rerender(<Composer costUsd={0.12} onSend={vi.fn()} running />);
    expect(screen.getByText("$0.12")).toBeTruthy();
  });

  it("çok küçük maliyeti dört basamakla gösterir, sıfıra yuvarlamaz", () => {
    render(<Composer costUsd={0.0042} onSend={vi.fn()} />);
    expect(screen.getByText("$0.0042")).toBeTruthy();
  });

  it("manuel Sohbet/Kod kip düğmesi artık hiç çizilmez (Faz 5, Görev 5 — tek kutu)", () => {
    render(<Composer onSend={vi.fn()} />);
    expect(screen.queryByRole("group", { name: "Çalışma kipi" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Sohbet" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Kod" })).toBeNull();
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

  it("IME composition sürerken Enter mesajı ya da slash komutunu göndermez", () => {
    const onSend = vi.fn();
    render(<Composer commands={[{
      ad: "mcp github",
      aciklama: "GitHub MCP sunucusu",
      grup: "MCP",
      kullanim: "",
      destekleniyor: true,
    }]} onSend={onSend} />);
    const textbox = screen.getByRole("textbox", { name: "Mesaj" });

    fireEvent.change(textbox, { target: { value: "/mcp github" } });
    const defaultAllowed = fireEvent.keyDown(textbox, { key: "Enter", isComposing: true });

    expect(onSend).not.toHaveBeenCalled();
    expect(textbox).toHaveProperty("value", "/mcp github");
    expect(defaultAllowed).toBe(true);
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

// Faz 5, Görev 5 ("tek kutu"): manuel Sohbet/Kod kip düğmesi kaldırıldı,
// backend artık her zaman `kod` (tam yetenek) varsayılanıyla başlıyor
// (bkz. `appserver/session.py`). Bu describe eskiden kip düğmelerini de
// test ediyordu; o testler silindi, klavye kısayolu testleri kaldı.
describe("Composer — izin modu klavye kısayolları", () => {
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

  it("IME composition sürerken Shift+Tab izin modunu değiştirmez", () => {
    const onApprovalChange = vi.fn();
    render(<Composer approval="auto" onApprovalChange={onApprovalChange} onSend={vi.fn()} />);
    const textbox = screen.getByRole("textbox", { name: "Mesaj" });

    const defaultAllowed = fireEvent.keyDown(textbox, { key: "Tab", shiftKey: true, isComposing: true });
    expect(onApprovalChange).not.toHaveBeenCalled();
    expect(defaultAllowed).toBe(true);
  });
});

describe("Composer — slash paleti ve ekler", () => {
  const commands = [
    { ad: "models", aciklama: "Modelleri listele", grup: "Model", kullanim: "", destekleniyor: true },
    { ad: "model", aciklama: "Modeli değiştir", grup: "Model", kullanim: "[alt-komut]", destekleniyor: true },
    { ad: "mode", aciklama: "Profili değiştir", grup: "Model", kullanim: "[profil]", destekleniyor: true },
    { ad: "mcp github", aciklama: "GitHub MCP sunucusu", grup: "MCP", kullanim: "", destekleniyor: true },
  ];

  it("/m yazınca eşleşmeleri gösterir; tıklama komutu inputa taşır", () => {
    const onSend = vi.fn();
    render(<Composer commands={commands} onSend={onSend} />);
    const textbox = screen.getByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "/m" } });

    expect(screen.getByRole("listbox", { name: "Komut önerileri" })).toBeTruthy();
    fireEvent.click(screen.getByRole("option", { name: /GitHub MCP sunucusu/i }));
    expect(textbox).toHaveProperty("value", "/mcp github");
    expect(onSend).not.toHaveBeenCalled();
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

  it.each(["/model", "/mode"])(
    "çakışan registry sırasında exact %s komutunu ilk öneriyle değiştirmeden çalıştırır",
    (typedCommand) => {
      const onSend = vi.fn();
      const onValueChange = vi.fn();
      render(
        <Composer
          commands={commands}
          onSend={onSend}
          onValueChange={onValueChange}
          value={typedCommand}
        />,
      );

      fireEvent.keyDown(screen.getByRole("textbox", { name: "Mesaj" }), { key: "Enter" });

      expect(onSend).toHaveBeenCalledWith(typedCommand);
      expect(onValueChange).toHaveBeenCalledWith("");
      expect(onValueChange).not.toHaveBeenCalledWith("/models");
    },
  );

  it("desteklenmeyen exact komutu Enter ile çalıştırmaz", () => {
    const onSend = vi.fn();
    render(<Composer commands={[{
      ad: "legacy",
      aciklama: "Eski komut",
      grup: "Komut",
      kullanim: "",
      destekleniyor: false,
    }]} onSend={onSend} />);
    const textbox = screen.getByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "/legacy" } });

    fireEvent.keyDown(textbox, { key: "Enter" });

    expect(onSend).not.toHaveBeenCalled();
    expect(textbox).toHaveProperty("value", "/legacy");
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

it("iş sürerken yazılabilir ve mesaj sıraya eklenir", () => {
  const gonderilen: string[] = [];
  render(<Composer onSend={(task) => gonderilen.push(task)} running />);

  const kutu = screen.getByLabelText("Mesaj") as HTMLTextAreaElement;
  expect(kutu.disabled).toBe(false);
  fireEvent.change(kutu, { target: { value: "sıradaki iş" } });
  fireEvent.click(screen.getByLabelText("Sıraya ekle"));

  expect(gonderilen).toEqual(["sıradaki iş"]);
});

it("Esc çalışan turu durdurur", () => {
  let durduruldu = false;
  render(<Composer onSend={() => undefined} onStop={() => { durduruldu = true; }} running />);

  fireEvent.keyDown(screen.getByLabelText("Mesaj"), { key: "Escape" });

  expect(durduruldu).toBe(true);
});

describe("maliyetRozetMetni", () => {
  it("null için null döner", () => {
    expect(maliyetRozetMetni(null)).toBeNull();
  });

  it("sıfır ya da negatif için null döner", () => {
    expect(maliyetRozetMetni(0)).toBeNull();
    expect(maliyetRozetMetni(-1)).toBeNull();
  });

  it("normal tutarı iki basamakla biçimlendirir", () => {
    expect(maliyetRozetMetni(1.5)).toBe("$1.50");
  });

  it("bir sentin altındaki tutarı dört basamakla biçimlendirir", () => {
    expect(maliyetRozetMetni(0.0042)).toBe("$0.0042");
  });
});

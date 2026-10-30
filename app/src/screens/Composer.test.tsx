import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Composer, maliyetRozetMetni } from "./Composer";

afterEach(cleanup);

describe("Composer", () => {
  it("kısa konuşmada tek satır, çok satırlı metin ve eklerde geniş düzen kullanır", () => {
    const { container, rerender } = render(<Composer onSend={vi.fn()} />);
    expect(container.querySelector(".composer")?.getAttribute("data-layout")).toBe("compact");
    expect(screen.getByRole("textbox", { name: "Mesaj" }).getAttribute("placeholder")).toBe("İstediğin bir şeyi sor");
    rerender(<Composer onSend={vi.fn()} value={"Birinci satır\nİkinci satır"} />);
    expect(container.querySelector(".composer")?.getAttribute("data-layout")).toBe("expanded");
    rerender(<Composer attachments={[{ kind: "file", name: "notlar.md", path: "/tmp/notlar.md" }]} onSend={vi.fn()} />);
    expect(container.querySelector(".composer")?.getAttribute("data-layout")).toBe("expanded");
  });

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
    expect(screen.getByRole("meter").textContent).toBe("Özetlemeye %17 kaldı");
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

  it("sohbet kipi seçildiğinde gündelik soru dili ve çalışma geçişini gösterir", () => {
    const onWorkspaceModeChange = vi.fn();
    render(<Composer onSend={vi.fn()} onWorkspaceModeChange={onWorkspaceModeChange} workspaceMode="sohbet" />);
    expect(screen.getByRole("textbox", { name: "Mesaj" }).getAttribute("placeholder")).toBe("İstediğin bir şeyi sor");
    fireEvent.click(screen.getByRole("button", { name: /Çalışma kipi: Sohbet/ }));
    expect(onWorkspaceModeChange).toHaveBeenCalledWith("kod");
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
    expect(onApprovalChange).toHaveBeenCalledWith("security");

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
    expect(screen.getByText("Manuel")).toBeTruthy();
    expect(screen.queryByText("Agent · Otomatik")).toBeNull();
  });

  it("Shift+Tab izin modunu Claude'daki sırayla döndürür; İzinleri atla döngüde yok", () => {
    const secilen: string[] = [];
    const { rerender } = render(
      <Composer approval="auto" onApprovalChange={(m) => secilen.push(m)} onSend={() => undefined} />,
    );
    for (const kip of ["security", "edits", "plan"] as const) {
      fireEvent.keyDown(screen.getByLabelText("Mesaj"), { key: "Tab", shiftKey: true });
      rerender(<Composer approval={kip} onApprovalChange={(m) => secilen.push(m)} onSend={() => undefined} />);
    }
    fireEvent.keyDown(screen.getByLabelText("Mesaj"), { key: "Tab", shiftKey: true });
    expect(secilen).toEqual(["security", "edits", "plan", "auto"]);
  });

  it("menüden açıklamalı beş kip seçilir; rakam tuşu da seçer", () => {
    const secilen: string[] = [];
    render(
      <Composer approval="plan" onApprovalChange={(m) => secilen.push(m)} onSend={() => undefined} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /İzin modu: Plan/ }));
    const secenekler = screen.getAllByRole("menuitemradio");
    expect(secenekler.map((s) => s.querySelector("strong")?.textContent)).toEqual([
      "Otomatik", "Manuel", "Düzenlemeleri kabul et", "Plan", "İzinleri atla",
    ]);
    expect(secenekler[3].getAttribute("aria-checked")).toBe("true");
    fireEvent.click(secenekler[2]);
    expect(secilen).toEqual(["edits"]);

    fireEvent.click(screen.getByRole("button", { name: /İzin modu: Plan/ }));
    fireEvent.keyDown(screen.getByRole("menu"), { key: "5" });
    expect(secilen).toEqual(["edits", "bypass"]);
    expect(screen.queryByRole("menu")).toBeNull();
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

describe("Composer — @ ile dosya anma", () => {
  const ONERILER = [
    { yol: "app/src/screens/Composer.tsx" },
    { yol: "src/fusion_cli/core/repo_map.py" },
  ];

  /** `@` yazılmış, önerileri gelmiş bir composer. */
  function anmaliComposer(overrides: Record<string, unknown> = {}) {
    const onFileQuery = vi.fn();
    const onSend = vi.fn();
    const utils = render(
      <Composer
        fileSuggestions={ONERILER}
        onFileQuery={onFileQuery}
        onSend={onSend}
        {...overrides}
      />,
    );
    const textbox = screen.getByRole("textbox", { name: "Mesaj" }) as HTMLTextAreaElement;
    fireEvent.change(textbox, { target: { value: "@comp", selectionStart: 5 } });
    return { ...utils, onFileQuery, onSend, textbox };
  }

  it("@ yazılınca sorguyu üst katmana bildirir", () => {
    const { onFileQuery } = anmaliComposer();
    expect(onFileQuery).toHaveBeenCalledWith("comp");
  });

  it("önerileri listeler", () => {
    anmaliComposer();
    const liste = screen.getByRole("listbox", { name: "Anma önerileri" });
    expect(liste).toBeTruthy();
    expect(screen.getByRole("option", { name: "app/src/screens/Composer.tsx" })).toBeTruthy();
  });

  it("tıklayınca anmayı seçilen yolla değiştirir", () => {
    const { textbox } = anmaliComposer();
    fireEvent.click(screen.getByRole("option", { name: "src/fusion_cli/core/repo_map.py" }));
    expect(textbox.value).toBe("@src/fusion_cli/core/repo_map.py ");
  });

  it("Enter listeyi seçer, mesajı GÖNDERMEZ", () => {
    // Anma açıkken Enter'ın turu başlatması, kullanıcının yarım yazdığı
    // dosya adını göreve çevirirdi.
    const { onSend, textbox } = anmaliComposer();
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
    expect(textbox.value).toBe("@app/src/screens/Composer.tsx ");
  });

  it("ok tuşlarıyla seçim gezinir", () => {
    const { textbox } = anmaliComposer();
    fireEvent.keyDown(textbox, { key: "ArrowDown" });
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(textbox.value).toBe("@src/fusion_cli/core/repo_map.py ");
  });

  it("Esc listeyi kapatır", () => {
    const { textbox } = anmaliComposer();
    fireEvent.keyDown(textbox, { key: "Escape" });
    expect(screen.queryByRole("listbox", { name: "Anma önerileri" })).toBeNull();
    expect(textbox.value).toBe("@comp");
  });

  it("onFileQuery verilmezse anma hiç açılmaz", () => {
    render(<Composer fileSuggestions={ONERILER} onSend={vi.fn()} />);
    const textbox = screen.getByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "@comp", selectionStart: 5 } });
    expect(screen.queryByRole("listbox", { name: "Anma önerileri" })).toBeNull();
  });

  it("öneri yoksa liste çizilmez", () => {
    render(<Composer fileSuggestions={[]} onFileQuery={vi.fn()} onSend={vi.fn()} />);
    const textbox = screen.getByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "@zzz", selectionStart: 4 } });
    expect(screen.queryByRole("listbox", { name: "Anma önerileri" })).toBeNull();
  });

  it("anma kapalıyken Enter normal gönderime döner", () => {
    const onSend = vi.fn();
    render(<Composer fileSuggestions={ONERILER} onFileQuery={vi.fn()} onSend={onSend} />);
    const textbox = screen.getByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "sıradan görev", selectionStart: 13 } });
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(onSend).toHaveBeenCalledWith("sıradan görev");
  });
});

it("tur sürerken ses düğmelerinin yerinde yuvarlak durdur düğmesi çıkar; boşken sıraya ekle görünmez", () => {
  let durdu = false;
  render(<Composer onSend={() => undefined} onStop={() => { durdu = true; }} onVoice={() => undefined} running />);

  expect(screen.queryByLabelText("Sıraya ekle")).toBeNull();
  expect(screen.queryByLabelText("Sesli konuşmayı aç")).toBeNull();
  const durdur = screen.getByRole("button", { name: "Durdur" });
  expect(durdur.className).toContain("composer__stop");
  fireEvent.click(durdur);
  expect(durdu).toBe(true);
});


describe("Composer — @ ile MCP seçimi", () => {
  const mcpServers = [
    { ad: "github", aciklama: "GitHub depoları" },
    { ad: "notion", aciklama: "Notion sayfaları" },
  ];

  function yaz(value: string, props: Partial<React.ComponentProps<typeof Composer>> = {}) {
    const onSend = vi.fn();
    const utils = render(
      <Composer mcpServers={mcpServers} onFileQuery={() => undefined} onSend={onSend} {...props} />,
    );
    const textbox = screen.getByRole("textbox", { name: "Mesaj" }) as HTMLTextAreaElement;
    fireEvent.change(textbox, { target: { value, selectionStart: value.length } });
    return { ...utils, onSend, textbox };
  }

  it("@ yazınca MCP sunucuları dosyalardan önce, MCP etiketiyle listelenir", () => {
    yaz("@git", { fileSuggestions: [{ yol: "src/github.ts" }] });
    const options = within(screen.getByRole("listbox", { name: "Anma önerileri" })).getAllByRole("option");
    expect(options[0].getAttribute("aria-label")).toBe("MCP github");
    expect(options[0].textContent).toContain("GitHub depoları · MCP");
    expect(options[1].getAttribute("aria-label")).toBe("src/github.ts");
    expect(screen.queryByRole("option", { name: "MCP notion" })).toBeNull();
  });

  it("MCP satırını seçince yazıya @ad olarak girer", () => {
    const { textbox } = yaz("bak @no");
    fireEvent.click(screen.getByRole("option", { name: "MCP notion" }));
    expect(textbox.value).toBe("bak @notion ");
  });

  it("Enter MCP satırını seçer, mesajı göndermez", () => {
    const { textbox, onSend } = yaz("@gi");
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
    expect(textbox.value).toBe("@github ");
  });

  // Ölçüldü (29 Ekim): `kontrol.durum` okunamayınca activeModel "" kalıyor ve seçici
  // `onModelSelect && activeModel` yüzünden tamamen kayboluyordu; kullanıcı
  // bozuk modelden başka modele geçemiyordu.
  it("etkin model okunamasa da model seçici görünür ve açılabilir kalır", () => {
    const onModelSelect = vi.fn();
    const modelOptions = [{ deger: "/model agent a/b", etiket: "Model B" }];
    const { rerender } = render(<Composer activeModel="" modelOptions={modelOptions} onModelSelect={onModelSelect} onSend={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Model: (seçilmedi|Model seç)/ }));
    fireEvent.click(screen.getByRole("option", { name: /Model B/ }));
    expect(onModelSelect).toHaveBeenCalledWith("/model agent a/b");
    rerender(<Composer activeModel="" modelOptions={modelOptions} onModelSelect={onModelSelect} onSend={vi.fn()} running />);
    expect(screen.getByRole("button", { name: /Model: (seçilmedi|Model seç)/ })).toBeTruthy();
  });
});

describe("Composer — P2/P3 ayıklama turu (dalga 4)", () => {
  it("sohbet kipinde Shift+Tab izin modunu sessizce değiştirmez (U1-03)", () => {
    const onApprovalChange = vi.fn();
    render(<Composer workspaceMode="sohbet" onWorkspaceModeChange={vi.fn()} onApprovalChange={onApprovalChange} onSend={vi.fn()} />);
    const textbox = screen.getByRole("textbox", { name: "Mesaj" });
    expect(fireEvent.keyDown(textbox, { key: "Tab", shiftKey: true })).toBe(true);
    expect(onApprovalChange).not.toHaveBeenCalled();
  });

  it("çalışma kipinde Shift+Tab izin modunu döndürmeyi sürdürür (U1-03)", () => {
    const onApprovalChange = vi.fn();
    render(<Composer workspaceMode="kod" onWorkspaceModeChange={vi.fn()} onApprovalChange={onApprovalChange} onSend={vi.fn()} />);
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Mesaj" }), { key: "Tab", shiftKey: true });
    expect(onApprovalChange).toHaveBeenCalledTimes(1);
  });

  it("gönderim beklenirken eklenen karakter korunur, gönderilen kısım silinir (U1-04)", async () => {
    let accept!: (value: unknown) => void;
    render(<Composer onSend={() => new Promise((resolve) => { accept = resolve; })} />);
    const textbox = screen.getByLabelText("Mesaj");
    fireEvent.change(textbox, { target: { value: "ilk görev" } });
    fireEvent.keyDown(textbox, { key: "Enter" });
    fireEvent.change(textbox, { target: { value: "ilk görevX" } });
    await act(async () => { accept({ requestId: "i", sessionId: "o", turnId: null, state: "accepted", error: null }); });
    expect(textbox).toHaveProperty("value", "X");
  });

  it("reddedilen gönderim hata gösterir ve kilidi açar (U1-05)", async () => {
    const onSend = vi.fn().mockRejectedValueOnce(new Error("ağ")).mockReturnValue(undefined);
    render(<Composer onSend={onSend} />);
    const textbox = screen.getByLabelText("Mesaj");
    fireEvent.change(textbox, { target: { value: "dene" } });
    await act(async () => { fireEvent.keyDown(textbox, { key: "Enter" }); });
    expect(screen.getByRole("alert").textContent).toContain("gönderilemedi");
    expect(textbox).toHaveProperty("value", "dene");
    await act(async () => { fireEvent.keyDown(textbox, { key: "Enter" }); });
    expect(onSend).toHaveBeenCalledTimes(2);
  });

  it("desteklenmeyen komutta Enter sessiz kalmaz ve modele ham komut gitmez (U1-06)", () => {
    const onSend = vi.fn();
    const commands = [{ ad: "denemecmd", aciklama: "x", grup: "g", kullanim: "/denemecmd", destekleniyor: false }];
    render(<Composer commands={commands} onSend={onSend} />);
    const textbox = screen.getByLabelText("Mesaj");
    fireEvent.change(textbox, { target: { value: "/denemecmd" } });
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(onSend).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toContain("desteklenmiyor");
  });

  it("palette Enter desteklenmeyen seçeneği kutuya yazmaz (U1-06)", () => {
    const commands = [{ ad: "denemecmd", aciklama: "x", grup: "g", kullanim: "/denemecmd", destekleniyor: false }];
    render(<Composer commands={commands} onSend={vi.fn()} />);
    const textbox = screen.getByLabelText("Mesaj");
    fireEvent.change(textbox, { target: { value: "/dene" } });
    fireEvent.keyDown(textbox, { key: "Enter" });
    expect(textbox).toHaveProperty("value", "/dene");
  });

  it("onFileQuery kimliği değişse de Esc ile kapatılan anma listesi yeniden açılmaz (U1-08)", () => {
    const sorgu = vi.fn();
    const oneriler = [{ yol: "src/a.ts" }];
    const { rerender } = render(<Composer onFileQuery={sorgu} fileSuggestions={oneriler} onSend={vi.fn()} />);
    const textbox = screen.getByLabelText("Mesaj");
    fireEvent.change(textbox, { target: { value: "@a", selectionStart: 2 } });
    expect(screen.getByRole("listbox", { name: "Anma önerileri" })).toBeTruthy();
    fireEvent.keyDown(textbox, { key: "Escape" });
    expect(screen.queryByRole("listbox", { name: "Anma önerileri" })).toBeNull();
    rerender(<Composer onFileQuery={(q) => sorgu(q)} fileSuggestions={oneriler} onSend={vi.fn()} />);
    expect(screen.queryByRole("listbox", { name: "Anma önerileri" })).toBeNull();
    expect(sorgu).toHaveBeenCalledTimes(1);
  });

  it("metin sürüklemesi iptal edilmez, dosya sürüklemesi edilir (U1-09)", () => {
    const onDropFiles = vi.fn();
    const { container } = render(<Composer onDropFiles={onDropFiles} onSend={vi.fn()} />);
    const kutu = container.querySelector(".composer")!;
    expect(fireEvent.drop(kutu, { dataTransfer: { types: ["text/plain"], files: [] } })).toBe(true);
    expect(onDropFiles).not.toHaveBeenCalled();
    expect(fireEvent.drop(kutu, { dataTransfer: { types: ["Files"], files: [new File(["x"], "a.txt")] } })).toBe(false);
    expect(onDropFiles).toHaveBeenCalledTimes(1);
  });

  it("panodaki görsel ek olarak eklenir, düz metin yapıştırma etkilenmez (U1-10)", () => {
    const onDropFiles = vi.fn();
    render(<Composer onDropFiles={onDropFiles} onSend={vi.fn()} />);
    const textbox = screen.getByLabelText("Mesaj");
    expect(fireEvent.paste(textbox, { clipboardData: { files: [] } })).toBe(true);
    const gorsel = new File(["x"], "ekran.png", { type: "image/png" });
    expect(fireEvent.paste(textbox, { clipboardData: { files: [gorsel] } })).toBe(false);
    expect(onDropFiles).toHaveBeenCalledWith([gorsel]);
  });

  it("IME kurulumundaki Esc çalışan turu durdurmaz (U1-12)", () => {
    const onStop = vi.fn();
    render(<Composer running onStop={onStop} onSend={vi.fn()} />);
    fireEvent.keyDown(screen.getByLabelText("Mesaj"), { key: "Escape", isComposing: true });
    expect(onStop).not.toHaveBeenCalled();
  });

  it("anma listesi açıkken Esc turu değil listeyi kapatır (U1-13)", () => {
    const onStop = vi.fn();
    render(<Composer running onStop={onStop} onFileQuery={vi.fn()} fileSuggestions={[{ yol: "a.ts" }]} onSend={vi.fn()} />);
    const textbox = screen.getByLabelText("Mesaj");
    fireEvent.change(textbox, { target: { value: "@a", selectionStart: 2 } });
    fireEvent.keyDown(textbox, { key: "Escape" });
    expect(onStop).not.toHaveBeenCalled();
    fireEvent.keyDown(textbox, { key: "Escape" });
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("açık palet textarea ile aria-controls/activedescendant üzerinden ilişkilidir (U1-14)", () => {
    const commands = [{ ad: "compact", aciklama: "x", grup: "g", kullanim: "/compact", destekleniyor: true }];
    render(<Composer commands={commands} onSend={vi.fn()} />);
    const textbox = screen.getByLabelText("Mesaj");
    expect(textbox.hasAttribute("aria-controls")).toBe(false);
    fireEvent.change(textbox, { target: { value: "/c" } });
    const liste = screen.getByRole("listbox", { name: "Komut önerileri" });
    expect(textbox.getAttribute("aria-controls")).toBe(liste.id);
    expect(document.getElementById(textbox.getAttribute("aria-activedescendant")!)?.getAttribute("role")).toBe("option");
  });

  it("Windows yolunda dosya adı ters eğik çizgiden bölünür (U1-19)", () => {
    render(<Composer onFileQuery={vi.fn()} fileSuggestions={[{ yol: "src\\ui\\App.tsx" }]} onSend={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Mesaj"), { target: { value: "@A", selectionStart: 2 } });
    expect(screen.getByText("@App.tsx")).toBeTruthy();
  });
});

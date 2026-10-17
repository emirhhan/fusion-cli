import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VoiceMode } from "./VoiceMode";
afterEach(cleanup);
describe("VoiceMode — yalnız karakter", () => {
  it("sol tık dinler ve çevresinde kontrol çizmez", () => {
    const onListen = vi.fn();
    const { container } = render(<VoiceMode listening onListen={onListen} onClose={vi.fn()} onMinimize={vi.fn()} state="listening" transcript="merhaba" />);
    fireEvent.click(screen.getByRole("button", { name: /Fusion.*dinle/i }));
    expect(onListen).toHaveBeenCalledOnce();
    expect(container.querySelector("header, footer")).toBeNull();
    expect(screen.getByText("merhaba").className).toBe("voice-panel__sr");
    expect(screen.queryByRole("menu")).toBeNull();
  });
  it.each([true, false])("sağ tık üç seçenek açar (geniş=%s)", (wide) => {
    const onMinimize = vi.fn();
    render(<VoiceMode listening onClose={vi.fn()} onMinimize={onMinimize} onWideChange={vi.fn()} onPrefsChange={vi.fn()} onTopChange={vi.fn()} state="idle" wide={wide} />);
    fireEvent.contextMenu(screen.getByRole("button", { name: /Fusion.*dinle/i }));
    expect(screen.getAllByRole("menuitem")).toHaveLength(3);
    expect(screen.queryByRole("menuitem", { name: /Görünümü/ })).toBeNull();
    fireEvent.click(screen.getByRole("menuitem", { name: "Simge durumuna küçült" }));
    expect(onMinimize).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).toBeNull();
  });
  it("gerçek hatayı gösterir", () => {
    render(<VoiceMode listening={false} onClose={vi.fn()} onMinimize={vi.fn()} state="error" transcript="macOS Dikte kapalı." />);
    expect(screen.getByRole("alert").textContent).toBe("macOS Dikte kapalı.");
    expect(screen.queryByText("Bir sorun oluştu")).toBeNull();
  });
});
describe("VoiceMode — onay", () => {
  const ASK = {
    acik: true,
    arac: "write_file",
    metin: "app.py dosyası yazılsın mı?",
    secenekler: [
      { deger: "evet", etiket: "Onayla" },
      { deger: "hayir", etiket: "Reddet" },
    ],
  };

  it("açık onayı panelde gösterir ve seçimi geri verir", () => {
    const onAnswer = vi.fn();
    render(
      <VoiceMode ask={ASK} listening={false} onAnswer={onAnswer} onClose={vi.fn()} onMinimize={vi.fn()} state="thinking" />,
    );
    expect(screen.getByText("app.py dosyası yazılsın mı?")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Sorunun tamamını oku" }));
    fireEvent.click(screen.getByRole("button", { name: "Reddet" }));
    expect(onAnswer).toHaveBeenCalledWith("hayir");
  });

  it("mini kipte de onayı erişilebilir kabul ve ret düğmeleriyle gösterir", () => {
    render(
      <VoiceMode ask={ASK} listening={false} onAnswer={vi.fn()} onClose={vi.fn()} onMinimize={vi.fn()} onWideChange={vi.fn()} state="approval" wide={false} />,
    );
    expect(screen.getByRole("group", { name: "Onay" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Sorunun tamamını oku" }));
    expect(screen.getByRole("button", { name: "Onayla" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reddet" })).toBeTruthy();

  });

  it("onay yokken hiçbir şey çizmez", () => {
    render(<VoiceMode ask={null} listening={false} onAnswer={vi.fn()} onClose={vi.fn()} onMinimize={vi.fn()} state="idle" />);
    expect(screen.queryByRole("group", { name: "Onay" })).toBeNull();
  });
});


it("karakteri sürüklemek pencereyi taşır, mikrofon tıklaması üretmez", () => {
 const onDrag = vi.fn(async () => {}); const onListen = vi.fn();
 render(<VoiceMode listening onDrag={onDrag} onListen={onListen} onClose={vi.fn()} onMinimize={vi.fn()} state="listening" />);
 const character = screen.getByRole("button", {name:/Fusion.*dinle/i});
 fireEvent(character, new MouseEvent("pointerdown", {bubbles:true, button:0, buttons:1, clientX:20,clientY:20}));
 fireEvent(character, new MouseEvent("pointermove", {bubbles:true, buttons:1, clientX:40,clientY:30}));
 fireEvent.click(character, {detail:1});
 expect(onDrag).toHaveBeenCalledOnce(); expect(onListen).not.toHaveBeenCalled();
 fireEvent(character, new MouseEvent("pointerdown", {bubbles:true, button:0,buttons:1,clientX:40,clientY:30}));
 fireEvent.click(character); expect(onListen).toHaveBeenCalledOnce();
});


it("taşıma sonrasında klavye aktivasyonu yutulmaz", () => {
 const onListen = vi.fn();
 render(<VoiceMode listening onDrag={async () => {}} onListen={onListen} onClose={vi.fn()} onMinimize={vi.fn()} state="listening" />);
 const character = screen.getByRole("button", {name:/Fusion.*dinle/i});
 fireEvent(character, new MouseEvent("pointerdown", {bubbles:true, button:0,buttons:1,clientX:0,clientY:0}));
 fireEvent(character, new MouseEvent("pointermove", {bubbles:true, buttons:1,clientX:20,clientY:0}));
 fireEvent.click(character, {detail:0});
 expect(onListen).toHaveBeenCalledOnce();
});

describe("VoiceMode — ChatGPT benzeri oturum denetimleri", () => {
  it("oturum kapalıyken yalnız 'Konuşmaya başla' görünür; Bitir/Sessize al yoktur", () => {
    const onListen = vi.fn();
    render(<VoiceMode listening={false} onListen={onListen} onClose={vi.fn()} onMinimize={vi.fn()} state="idle" />);
    expect(screen.queryByRole("button", { name: "Bitir" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Sessize al" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Konuşmaya başla" }));
    expect(onListen).toHaveBeenCalledOnce();
  });

  it("oturum açıkken Sessize al ve Bitir her zaman görünür ve çalışır", () => {
    const onEnd = vi.fn();
    const onMute = vi.fn();
    render(
      <VoiceMode listening sessionOpen onEnd={onEnd} onMute={onMute} onClose={vi.fn()} onMinimize={vi.fn()} state="listening" />,
    );
    expect(screen.queryByRole("button", { name: "Konuşmaya başla" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Sessize al" }));
    fireEvent.click(screen.getByRole("button", { name: "Bitir" }));
    expect(onMute).toHaveBeenCalledOnce();
    expect(onEnd).toHaveBeenCalledOnce();
  });

  it("sessizdeyken düğme 'Sesi aç' der ve basılı durumu bildirir", () => {
    render(
      <VoiceMode listening={false} sessionOpen muted onEnd={vi.fn()} onMute={vi.fn()} onClose={vi.fn()} onMinimize={vi.fn()} state="idle" />,
    );
    expect(screen.getByRole("button", { name: "Sesi aç" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("Fusion konuşurken karakter söz keser; oturum açıkken boştayken tıklama hiçbir şey başlatmaz", () => {
    const onInterrupt = vi.fn();
    const onListen = vi.fn();
    const { rerender } = render(
      <VoiceMode listening sessionOpen onInterrupt={onInterrupt} onListen={onListen} onClose={vi.fn()} onMinimize={vi.fn()} state="talking" />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Fusion.*dinle/i }));
    expect(onInterrupt).toHaveBeenCalledOnce();
    rerender(<VoiceMode listening sessionOpen onInterrupt={onInterrupt} onListen={onListen} onClose={vi.fn()} onMinimize={vi.fn()} state="listening" />);
    fireEvent.click(screen.getByRole("button", { name: /Fusion.*dinle/i }));
    expect(onListen).not.toHaveBeenCalled();
  });
});

it("düşünürken ekranda 'Hmm…' görünür, başka durumda görünmez", () => {
  const { rerender } = render(<VoiceMode listening sessionOpen onClose={vi.fn()} onMinimize={vi.fn()} state="thinking" />);
  expect(screen.getByText("Hmm…")).toBeTruthy();
  rerender(<VoiceMode listening sessionOpen onClose={vi.fn()} onMinimize={vi.fn()} state="listening" />);
  expect(screen.queryByText("Hmm…")).toBeNull();
});

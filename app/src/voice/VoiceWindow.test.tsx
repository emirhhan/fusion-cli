import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VoiceWindow, matchSpokenAnswer, type VoiceWindowRuntime } from "./VoiceWindow";
import type { VoiceAsk, VoicePrefsPayload, VoiceRuntimeState } from "./bridge";

vi.mock("./level", () => ({ startLevelMeter: vi.fn(async () => null) }));

afterEach(cleanup);

const ASK: VoiceAsk = {
  acik: true,
  arac: "write_file",
  metin: "Dosya yazılsın mı?",
  secenekler: [
    { deger: "evet", etiket: "Onayla" },
    { deger: "hayir", etiket: "Reddet" },
  ],
};

function fakeRuntime() {
  let recognition: ((line: string) => void) | null = null;
  let ask: ((value: VoiceAsk | null) => void) | null = null;
  let prefs: ((value: VoicePrefsPayload) => void) | null = null;
  let runtimeState: ((value: VoiceRuntimeState) => void) | null = null;
  const runtime: VoiceWindowRuntime = {
    applyGeometry: vi.fn(async () => undefined),
    answerAsk: vi.fn(async () => undefined),
    close: vi.fn(async () => undefined),
    emitMessage: vi.fn(async () => undefined),
    onAsk: vi.fn(async (handler) => { ask = handler; return () => undefined; }),
    onPrefs: vi.fn(async (handler) => { prefs = handler; return () => undefined; }),
    onRecognition: vi.fn(async (handler) => { recognition = handler; return () => undefined; }),
    onRuntimeState: vi.fn(async (handler) => { runtimeState = handler; return () => undefined; }),
    onWindowGeometry: vi.fn(async () => () => undefined),
    pickModel: vi.fn(async () => null),
    requestPrefs: vi.fn(async () => undefined),
    startRecognition: vi.fn(async () => undefined),
    stopRecognition: vi.fn(async () => undefined),
  };
  return {
    ask: (value: VoiceAsk | null) => ask?.(value),
    prefs: (value: VoicePrefsPayload) => prefs?.(value),
    recognition: (value: object) => recognition?.(JSON.stringify(value)),
    runtime,
    runtimeState: (value: VoiceRuntimeState) => runtimeState?.(value),
  };
}

describe("VoiceWindow — aynı sohbet ve mikrofon yaşam döngüsü", () => {
  it("kısmiyi yalnız gösterir, kesin sonucu bir kez sohbete yollar", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);

    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(1));
    fake.recognition({ tur: "kismi", metin: "merha" });
    expect(await screen.findByText("merha")).toBeTruthy();
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();

    fake.recognition({ tur: "son", metin: "merhaba" });
    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledTimes(1));
    expect(fake.runtime.emitMessage).toHaveBeenCalledWith({ kaynak: "kullanici", metin: "merhaba" });
    fake.recognition({ tur: "son", metin: "merhaba" });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fake.runtime.emitMessage).toHaveBeenCalledTimes(1);
  });

  it("Fusion konuşurken mikrofonu kapatır, bitince yeniden dinler", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(1));

    fake.runtimeState({ durum: "talking", metin: "Merhaba" });
    await waitFor(() => expect(fake.runtime.stopRecognition).toHaveBeenCalledTimes(1));
    expect(screen.getByText("Konuşuyorum")).toBeTruthy();

    fake.runtimeState({ durum: "listening" });
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2));
    expect(screen.getByText("Dinliyorum…")).toBeTruthy();
  });

  it("mikrofon düğmesi dinlemeyi gerçekten durdurur", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("button", { name: "Dinlemeyi durdur" }));
    await waitFor(() => expect(fake.runtime.stopRecognition).toHaveBeenCalledTimes(1));
  });
});

describe("VoiceWindow — sesli onay", () => {
  it("yalnız açık ve tek anlamlı cevabı eşler", () => {
    expect(matchSpokenAnswer("evet", ASK)).toBe("evet");
    expect(matchSpokenAnswer("onayla", ASK)).toBe("evet");
    expect(matchSpokenAnswer("hayır", ASK)).toBe("hayir");
    expect(matchSpokenAnswer("olabilir ama emin değilim", ASK)).toBeNull();
  });

  it("eşleşen cevabı onaya yollar, normal sohbet mesajına dönüştürmez", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(1));
    fake.ask(ASK);
    expect(await screen.findByRole("group", { name: "Onay" })).toBeTruthy();

    fake.recognition({ tur: "son", metin: "onayla" });
    await waitFor(() => expect(fake.runtime.answerAsk).toHaveBeenCalledWith("evet"));
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
  });
});

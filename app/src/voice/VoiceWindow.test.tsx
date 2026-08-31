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
  let recognition: ((event: { session: number; line: string }) => void) | null = null;
  let ask: ((value: VoiceAsk | null) => void) | null = null;
  let prefs: ((value: VoicePrefsPayload) => void) | null = null;
  let runtimeState: ((value: VoiceRuntimeState) => void) | null = null;
  let recognitionEnded: ((event: { session: number; reason: string | null }) => void) | null = null;
  const runtime: VoiceWindowRuntime = {
    applyGeometry: vi.fn(async () => undefined),
    answerAsk: vi.fn(async () => undefined),
    close: vi.fn(async () => undefined),
    emitMessage: vi.fn(async () => undefined),
    onAsk: vi.fn(async (handler) => { ask = handler; return () => undefined; }),
    onPrefs: vi.fn(async (handler) => { prefs = handler; return () => undefined; }),
    onRecognition: vi.fn(async (handler) => { recognition = handler; return () => undefined; }),
    onRecognitionEnded: vi.fn(async (handler) => { recognitionEnded = handler; return () => undefined; }),
    onRuntimeState: vi.fn(async (handler) => { runtimeState = handler; return () => undefined; }),
    onWindowGeometry: vi.fn(async () => () => undefined),
    pickModel: vi.fn(async () => null),
    preflightRecognition: vi.fn(async () => true),
    requestPrefs: vi.fn(async () => undefined),
    startRecognition: vi.fn(async () => undefined),
    stopRecognition: vi.fn(async () => undefined),
  };
  return {
    ask: (value: VoiceAsk | null) => ask?.(value),
    prefs: (value: VoicePrefsPayload) => prefs?.(value),
    recognition: (value: object, session = 1) => recognition?.({ session, line: JSON.stringify(value) }),
    recognitionEnded: (reason: string | null = null, session = 1) => recognitionEnded?.({ session, reason }),
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

  it("recognition dinleyicilerini mikrofon sürecinden önce kurar", async () => {
    const fake = fakeRuntime();
    const order: string[] = [];
    vi.mocked(fake.runtime.onRecognition).mockImplementation(async () => {
      order.push("listener");
      return () => undefined;
    });
    vi.mocked(fake.runtime.startRecognition).mockImplementation(async () => { order.push("start"); });
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(order).toContain("start"));
    expect(order.indexOf("listener")).toBeLessThan(order.indexOf("start"));
  });

  it("eski oturum çıktısını ve bitişini yeni oturuma karıştırmaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Dinlemeyi durdur" }));
    await waitFor(() => expect(fake.runtime.stopRecognition).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Konuşmaya başla" }));
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2));

    fake.recognition({ tur: "son", metin: "eski mesaj" }, 1);
    fake.recognitionEnded("eski süreç kapandı", 1);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
    expect(screen.queryByText("eski süreç kapandı")).toBeNull();

    fake.recognition({ tur: "son", metin: "yeni mesaj" }, 2);
    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledOnce());
    expect(fake.runtime.emitMessage).toHaveBeenCalledWith({ kaynak: "kullanici", metin: "yeni mesaj" });
  });

  it("mini ve normal görünüm geçişinde recognition sürecini kesmez", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fireEvent.click(screen.getByRole("button", { name: "Paneli küçült" }));
    fireEvent.click(screen.getByRole("button", { name: "Paneli büyüt" }));

    expect(fake.runtime.stopRecognition).not.toHaveBeenCalled();
    expect(fake.runtime.startRecognition).toHaveBeenCalledOnce();
  });

  it("izin verilmezse mikrofon tıklaması süreci başlatmaz ve tekrar denetir", async () => {
    const fake = fakeRuntime();
    vi.mocked(fake.runtime.preflightRecognition)
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);
    render(<VoiceWindow runtime={fake.runtime} />);

    expect(await screen.findByText("Mikrofon izni verilmedi. İzin verdikten sonra yeniden deneyin.")).toBeTruthy();
    expect(fake.runtime.startRecognition).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Konuşmaya başla" }));
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
  });

  it("beklenmedik çıkıştan sonra mikrofon düğmesi yeni oturumla tekrar dener", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.recognitionEnded("Yardımcı beklenmedik kapandı", 1);
    expect(await screen.findByText("Yardımcı beklenmedik kapandı")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Konuşmaya başla" }));
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2));
  });

  it("recognition beklenmedik biterse dinliyorum durumunda kalmaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.recognitionEnded("Yardımcı beklenmedik kapandı");
    expect(await screen.findByText("Yardımcı beklenmedik kapandı")).toBeTruthy();
    expect(screen.getByText("Bir sorun oluştu")).toBeTruthy();
  });

  it("TTS bitişindeki start, geciken stop tamamlanmadan çalışmaz", async () => {
    const fake = fakeRuntime();
    let finishStop: (() => void) | null = null;
    vi.mocked(fake.runtime.stopRecognition).mockImplementation(() => new Promise<void>((resolve) => {
      finishStop = resolve;
    }));
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.runtimeState({ durum: "talking", metin: "Yanıt" });
    await waitFor(() => expect(fake.runtime.stopRecognition).toHaveBeenCalledOnce());
    fake.runtimeState({ durum: "listening" });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fake.runtime.startRecognition).toHaveBeenCalledOnce();
    finishStop?.();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2));
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

  it("belirsiz onayı fail-closed tutar ve sohbet turuna dönüştürmez", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.ask(ASK);
    fake.recognition({ tur: "son", metin: "olabilir ama emin değilim" });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fake.runtime.answerAsk).not.toHaveBeenCalled();
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
    expect(screen.getByRole("group", { name: "Onay" })).toBeTruthy();
  });
});

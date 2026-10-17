import * as cues from "./cues";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PermissionBridge } from "../permissions/types";
import { VoiceWindow, matchSpokenAnswer, type VoiceWindowRuntime } from "./VoiceWindow";
import type { VoiceAsk, VoicePrefsPayload, VoiceRuntimeState } from "./bridge";

vi.mock("./level", () => ({ startLevelMeter: vi.fn(async () => null) }));

afterEach(cleanup);

/** Talk artık ChatGPT gibi oturumla çalışır: mikrofon yalnız kullanıcı başlatınca açılır. */
async function startTalk() {
  // İnsan, dinleyiciler kurulmadan butona basamaz; test de kurulumu bekler.
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
  fireEvent.click(screen.getByRole("button", { name: /Mikrofon kapalı/ }));
  // İlk kullanımdaki izin açıklamaları (mikrofon, konuşma tanıma) varsa devam et.
  for (let step = 0; step < 3; step += 1) {
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 5)); });
    const next = screen.queryByRole("button", { name: /Devam et/i });
    if (!next) break;
    fireEvent.click(next);
  }
}

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
    interruptSpeech: vi.fn(async () => undefined),
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
    recognition: (value: object, session = 1) => recognition?.({
      session,
      line: JSON.stringify({ guven: 0.9, speech_ms: 500, segment: 1, ...value }),
    }),
    recognitionEnded: (reason: string | null = null, session = 1) => recognitionEnded?.({ session, reason }),
    runtime,
    runtimeState: (value: VoiceRuntimeState) => runtimeState?.(value),
  };
}

describe("VoiceWindow — aynı sohbet ve mikrofon yaşam döngüsü", () => {
  it("first Talk activation gates microphone and speech through preflightRecognition", async () => {
    const fake = fakeRuntime();
    const requested: string[] = [];
    const permissionBridge: PermissionBridge = {
      request: vi.fn(async (kind) => { requested.push(kind); return "granted"; }),
      openSettings: vi.fn(),
    };
    render(<VoiceWindow permissionBridge={permissionBridge} runtime={fake.runtime} />);

    // Pencere açılınca izin istenmez ve mikrofon açılmaz; yalnız kullanıcı başlatınca.
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); });
    expect(requested).toEqual([]);
    expect(fake.runtime.startRecognition).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Mikrofon kapalı/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Devam et/i }));
    await waitFor(() => expect(requested).toEqual(["microphone"]));
    fireEvent.click(await screen.findByRole("button", { name: /Devam et/i }));

    await waitFor(() => expect(requested).toEqual(["microphone", "speech"]));
    expect(fake.runtime.preflightRecognition).toHaveBeenCalledOnce();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
  });

  it("dört taze oturumu farklı metinlerle birer kez yollar, sessiz beşinci turu yollamaz", { timeout: 20_000 }, async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    const texts = ["birinci mesaj", "ikinci mesaj", "üçüncü mesaj", "dördüncü mesaj"];
    for (let index = 0; index < texts.length; index += 1) {
      const session = index + 1;
      fake.recognition({ tur: "ses-basladi", metin: "", guven: null, speech_ms: 80 }, session);
      fake.recognition({ tur: "son", metin: texts[index] }, session);
      await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledTimes(index + 1));
      fake.recognitionEnded(null, session);
      // Yeniden başlatma KENDİLİĞİNDEN olur; basılacak bir tuş yok.
      await waitFor(
        () => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(index + 2),
        { timeout: 3_000 },
      );
    }

    fake.recognition({ tur: "ses-bitti", metin: "", guven: null, speech_ms: 0 }, 5);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fake.runtime.emitMessage.mock.calls.map(([message]) => message.metin)).toEqual(texts);
  });

  it("yerel sıfır güvenli konuşmayı aynı sohbete bir kez yollar", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.recognition({ tur: "son", metin: "Projeyi şimdi aç", guven: 0, speech_ms: 720 });
    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledOnce());
    expect(fake.runtime.emitMessage).toHaveBeenCalledWith({ kaynak: "kullanici", metin: "Projeyi şimdi aç" });
  });

  it("sessizlik kaynaklı düşük güvenli Evet tekrarını ne gösterir ne yollar", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fake.recognition({ tur: "kismi", metin: "Evet", guven: 0.08, speech_ms: 0 });
    await new Promise((resolve) => setTimeout(resolve, 1_500));

    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
    expect(screen.queryByText("Evet")).toBeNull();
  });

  it("reddedilen final sırasında etkin recognition sahipliğini durdurma eylemiyle gösterir", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fake.recognition({ tur: "son", metin: "belirsiz", guven: 0.1, speech_ms: 420 });
    await waitFor(() => expect(screen.getByRole("region", { name: "Fusion Talk" }).getAttribute("data-state")).toBe("interrupted"));

    // Sahiplik artık tuşla değil göstergeyle bildirilir.
    expect(screen.getByRole("status", { name: "Dinliyor" })).toBeTruthy();
    expect(fake.runtime.startRecognition).toHaveBeenCalledOnce();
  });
  it("kısmiyi yalnız gösterir, kesin sonucu bir kez sohbete yollar", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();

    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(1));
    fake.recognition({ tur: "kismi", metin: "merha" });
    expect((await screen.findAllByText("merha")).length).toBeGreaterThan(0); // sr + görünür yazı
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();

    fake.recognition({ tur: "son", metin: "merhaba" });
    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledTimes(1));
    expect(fake.runtime.emitMessage).toHaveBeenCalledWith({ kaynak: "kullanici", metin: "merhaba" });
    fake.recognition({ tur: "son", metin: "merhaba" });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fake.runtime.emitMessage).toHaveBeenCalledTimes(1);
  });

  it("Apple final vermese de duran kısmi metni hızlıca kesinleştirir", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();

    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.recognition({ tur: "kismi", metin: "merhaba fusion" });

    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledWith({
      kaynak: "kullanici",
      metin: "merhaba fusion",
    }), { timeout: 4_000 });
    expect(fake.runtime.stopRecognition).toHaveBeenCalledOnce();
  });

  it("kısa düşünme duraklamasında cümleyi erken kesmez", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fake.recognition({ tur: "kismi", metin: "merhaba" });
    await new Promise((resolve) => setTimeout(resolve, 1_000));
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
    fake.recognition({ tur: "son", metin: "merhaba fusion" });

    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledWith({
      kaynak: "kullanici",
      metin: "merhaba fusion",
    }));
  });

  it("Fusion konuşurken VAD'i korur ve ses-basladi olayinda barge-in bildirir", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(1));

    fake.runtimeState({ durum: "talking", metin: "Merhaba" });
    await screen.findByText("Konuşuyorum");
    expect(fake.runtime.stopRecognition).not.toHaveBeenCalled();

    fake.recognition({ tur: "ses-basladi", metin: "", guven: null, speech_ms: 80 });
    expect(fake.runtime.interruptSpeech).not.toHaveBeenCalled();
    fake.recognition({ tur: "kismi", metin: "araya girdim", guven: 0.92, speech_ms: 520 });
    await waitFor(() => expect(fake.runtime.interruptSpeech).toHaveBeenCalledOnce());

    fake.runtimeState({ durum: "interrupted" });
    fake.runtimeState({ durum: "listening" });
    expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(1);
    await screen.findAllByText("araya girdim");
  });

  it("barge-in tamponlarini TTS iptal onayindan once kabul etmez", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fake.runtimeState({ durum: "talking", metin: "Uzun yanit" });
    await screen.findByText("Konuşuyorum");
    fake.recognition({ tur: "ses-basladi", metin: "", guven: null, speech_ms: 80 });
    expect(fake.runtime.interruptSpeech).not.toHaveBeenCalled();
    fake.recognition({ tur: "kismi", metin: "araya girdim", guven: 0.92, speech_ms: 520 });
    await waitFor(() => expect(fake.runtime.interruptSpeech).toHaveBeenCalledOnce());
    fake.recognition({ tur: "son", metin: "araya girdim", guven: 0.92, speech_ms: 520 });
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();

    fake.runtimeState({ durum: "interrupted" });
    // Kesilen cevap BAĞLAM olarak gider: modele "sözüm burada kesildi" bilgisi
    // gitmezse kullanıcının düzeltmesi bağlamsız kalır ve Fusion yeni bir soru
    // almış gibi davranır.
    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledWith({
      kaynak: "kullanici",
      metin: "araya girdim",
      kesilen: "Uzun yanit",
    }));
  });

  it("sozu kesilmeden gelen konusmaya kesilen baglami eklemez", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fake.recognition({ tur: "son", metin: "merhaba", guven: 0.95, speech_ms: 600 });

    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledWith({
      kaynak: "kullanici",
      metin: "merhaba",
    }));
  });

  it("TTS iptali basarisizsa eski tamponu atar ve taze retry konusmasini kabul eder", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fake.runtimeState({ durum: "talking", metin: "Uzun yanit" });
    await screen.findByText("Konuşuyorum");
    fake.recognition({ tur: "ses-basladi", metin: "", guven: null, speech_ms: 80 });
    fake.recognition({ tur: "son", metin: "eski tampon", guven: 0.95, speech_ms: 600 });
    fake.runtimeState({ durum: "error", metin: "Ses kesilemedi. Tekrar deneyin." });

    expect(await screen.findByText("Ses kesilemedi. Tekrar deneyin.")).toBeTruthy();
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
    await waitFor(() => expect(fake.runtime.stopRecognition).toHaveBeenCalledOnce());

    // Basılacak tuş yok: durdurulan oturumun bitişi dinlemeyi geri getirir.
    fake.recognitionEnded(null, 1);
    await waitFor(
      () => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2),
      { timeout: 3_000 },
    );
    fake.recognition({ tur: "ses-basladi", metin: "", guven: null, speech_ms: 80 }, 2);
    fake.recognition({ tur: "son", metin: "taze soz", guven: 0.94, speech_ms: 520 }, 2);

    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledWith({
      kaynak: "kullanici",
      metin: "taze soz",
    }));
    expect(fake.runtime.emitMessage).not.toHaveBeenCalledWith({
      kaynak: "kullanici",
      metin: "eski tampon",
    });
  });

  it("dinlemeyi durduran bir kullanici eylemi SUNMAZ", async () => {
    // Mikrofon tuşu kaldırıldı: Talk açıkken dinleme sürekli açıktır ve
    // konuşmak için hiçbir şeye basılmaz.
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(1));

    expect(screen.queryByRole("button", { name: "Dinlemeyi durdur" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Konuşmaya başla" })).toBeNull();
    expect(screen.getByRole("status", { name: "Dinliyor" })).toBeTruthy();
  });

  it("recognition dinleyicilerini mikrofon sürecinden önce kurar", async () => {
    const fake = fakeRuntime();
    const order: string[] = [];
    vi.mocked(fake.runtime.onRecognition).mockImplementation(async () => {
      order.push("listener");
      return () => undefined;
    });
    vi.mocked(fake.runtime.startRecognition).mockImplementation(async () => { order.push("start"); });
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(order).toContain("start"));
    expect(order.indexOf("listener")).toBeLessThan(order.indexOf("start"));
  });

  it("start tokenı dönmeden gelen hızlı final ve bitişi işler", async () => {
    const fake = fakeRuntime();
    vi.mocked(fake.runtime.startRecognition).mockImplementation(async () => {
      fake.recognition({ tur: "son", metin: "anında tamam" }, 9);
      fake.recognitionEnded(null, 9);
      return 9;
    });
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();

    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledWith({
      kaynak: "kullanici",
      metin: "anında tamam",
    }));
  });

  it("bekleyen izin denetimi durdurulunca eski start isteğini başlatmaz", async () => {
    const fake = fakeRuntime();
    let resolvePreflight: ((granted: boolean) => void) | null = null;
    vi.mocked(fake.runtime.preflightRecognition).mockImplementation(() => new Promise<boolean>((resolve) => {
      resolvePreflight = resolve;
    }));
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();

    await waitFor(() => expect(fake.runtime.preflightRecognition).toHaveBeenCalledOnce());
    // Talk kapanınca bekleyen izin denetimi eski isteği başlatmamalı.
    cleanup();
    resolvePreflight?.(true);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(fake.runtime.startRecognition).not.toHaveBeenCalled();
  });

  it("aynı oturumun farklı ikinci finalini sohbete ikinci kez yollamaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fake.recognition({ tur: "son", metin: "ilk" });
    fake.recognition({ tur: "son", metin: "ikinci" });

    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledOnce());
    expect(fake.runtime.emitMessage).toHaveBeenCalledWith({ kaynak: "kullanici", metin: "ilk" });
  });

  it("eski oturum çıktısını ve bitişini yeni oturuma karıştırmaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.recognitionEnded("süreç kapandı", 1);
    await waitFor(
      () => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2),
      { timeout: 3_000 },
    );

    fake.recognition({ tur: "son", metin: "eski mesaj" }, 1);
    fake.recognitionEnded("eski süreç kapandı", 1);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
    expect(screen.queryByText("eski süreç kapandı")).toBeNull();

    fake.recognition({ tur: "son", metin: "yeni mesaj" }, 2);
    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledOnce());
    expect(fake.runtime.emitMessage).toHaveBeenCalledWith({ kaynak: "kullanici", metin: "yeni mesaj" });
  });

  it("mini menü açılıp kapanırken recognition sürecini kesmez", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fireEvent.contextMenu(screen.getByRole("button", { name: /Fusion.*dinle/i }));
    fireEvent.contextMenu(screen.getByRole("button", { name: /Fusion.*dinle/i }));

    expect(fake.runtime.stopRecognition).not.toHaveBeenCalled();
    expect(fake.runtime.startRecognition).toHaveBeenCalledOnce();
  });

  it("izin verilmezse süreci başlatmaz, oturumu kapatır ve kullanıcı yeniden başlatınca dener", async () => {
    const fake = fakeRuntime();
    vi.mocked(fake.runtime.preflightRecognition)
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();

    expect(await screen.findByText("Mikrofon izni verilmedi. İzin verdikten sonra yeniden deneyin.")).toBeTruthy();
    expect(fake.runtime.startRecognition).not.toHaveBeenCalled();
    // Mikrofon kendiliğinden tekrar açılmaz; oturum kapalıdır ve düğme yeniden başlatır.
    await new Promise((resolve) => setTimeout(resolve, 900));
    expect(fake.runtime.startRecognition).not.toHaveBeenCalled();
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
  });

  it("beklenmedik cikistan sonra dinleme kendiliginden toparlanir", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.recognitionEnded("Yardımcı beklenmedik kapandı", 1);
    expect(await screen.findByText("Yardımcı beklenmedik kapandı")).toBeTruthy();

    // Basılacak tuş yok: uygulama geri çekilmeyle kendi toparlanır.
    await waitFor(
      () => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2),
      { timeout: 3_000 },
    );
  });

  it("recognition beklenmedik biterse dinliyorum durumunda kalmaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.recognitionEnded("Yardımcı beklenmedik kapandı");
    expect(await screen.findByText("Yardımcı beklenmedik kapandı")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toBe("Yardımcı beklenmedik kapandı");
  });

  it("normal TTS bitisinde dusuk gecikmeli VAD oturumunu yeniden baslatmaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.runtimeState({ durum: "talking", metin: "Yanıt" });
    await screen.findByText("Konuşuyorum");
    fake.runtimeState({ durum: "listening" });
    await screen.findByText("Dinliyorum…");
    expect(fake.runtime.startRecognition).toHaveBeenCalledOnce();
    expect(fake.runtime.stopRecognition).not.toHaveBeenCalled();
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
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(1));
    fake.ask(ASK);
    expect(await screen.findByRole("group", { name: "Onay" })).toBeTruthy();

    fake.recognition({ tur: "son", metin: "onayla" });
    await waitFor(() => expect(fake.runtime.answerAsk).toHaveBeenCalledWith("evet", ASK));
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
  });

  it("aynı turdaki ikinci finalin onayı iki kez çalıştırmasını engeller", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.ask(ASK);
    await screen.findByRole("group", { name: "Onay" });

    fake.recognition({ tur: "son", metin: "onayla" });
    fake.recognition({ tur: "son", metin: "onayla" });

    await waitFor(() => expect(fake.runtime.answerAsk).toHaveBeenCalledOnce());
    expect(fake.runtime.answerAsk).toHaveBeenCalledWith("evet", ASK);
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
  });

  it("belirsiz onayı fail-closed tutar ve sohbet turuna dönüştürmez", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.ask(ASK);
    fake.recognition({ tur: "son", metin: "olabilir ama emin değilim" });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fake.runtime.answerAsk).not.toHaveBeenCalled();
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
    expect(screen.getByRole("group", { name: "Onay" })).toBeTruthy();
  });

  it("eski belirsiz onayın yeniden başlatma niyetini yeni oturum sonuna taşımaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.ask(ASK);

    fake.recognition({ tur: "son", metin: "olabilir ama emin değilim" }, 1);
    fake.recognitionEnded("oturum bitti", 1);
    await waitFor(
      () => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2),
      { timeout: 3_000 },
    );
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2));

    fake.recognitionEnded(null, 1);
    fake.recognitionEnded("yeni oturum kapandı", 2);

    expect(await screen.findByText("yeni oturum kapandı")).toBeTruthy();
    expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2);
  });

  it("kısmi belirsiz onayı göndermeden yeni dinleme oturumu açar", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.ask(ASK);

    fake.recognition({ tur: "kismi", metin: "olabilir ama emin değilim" });

    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2), { timeout: 4_000 });
    expect(fake.runtime.answerAsk).not.toHaveBeenCalled();
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
    expect(screen.getByRole("group", { name: "Onay" })).toBeTruthy();
  });

  it("önceki kısmi eveti sonradan açılan onaya uygulamaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fake.recognition({ tur: "kismi", metin: "evet" });
    fake.ask(ASK);
    await new Promise((resolve) => setTimeout(resolve, 1_500));

    expect(fake.runtime.answerAsk).not.toHaveBeenCalled();
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
  });

  it("stop bitmeden gelen ended olayında belirsiz onayı tam bir kez yeniden dinler", async () => {
    const fake = fakeRuntime();
    vi.mocked(fake.runtime.stopRecognition).mockImplementation(async () => {
      fake.recognitionEnded(null, 1);
    });
    render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.ask(ASK);

    fake.recognition({ tur: "kismi", metin: "olabilir ama emin değilim" });

    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2), { timeout: 4_000 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2);
  });
});

it("eski soruya ait konuşma yeni soru geldiğinde onaya dönüşmez", async () => {
  localStorage.setItem("fusion.permission-explanations.v1", JSON.stringify({ microphone: true, speech: true }));
  const fake = fakeRuntime();
  render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
  await startTalk();
  await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
  fake.ask({ ...ASK, questionId: "old", sessionId: "offline" });
  await screen.findByRole("group", { name: "Onay" });
  fake.recognition({ tur: "kismi", metin: "onayla" });
  fake.ask({ ...ASK, questionId: "new", sessionId: "offline" });
  fake.recognition({ tur: "son", metin: "onayla" });
  await waitFor(() => expect(screen.getByRole("group", { name: "Onay" })).toBeTruthy());
  expect(fake.runtime.answerAsk).not.toHaveBeenCalled();
});


it("eski kısmi konuşmanın zaman aşımı yeni soruyu onaylayamaz", async () => {
  localStorage.setItem("fusion.permission-explanations.v1", JSON.stringify({ microphone: true, speech: true }));
  const explicitAsk = { ...ASK, secenekler: [{ deger: "once", etiket: "İzin ver" }, { deger: "deny", etiket: "Reddet" }] };
  const fake = fakeRuntime();
  render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
  await startTalk();
  await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
  act(() => fake.ask({ ...explicitAsk, questionId: "old", sessionId: "offline" }));
  act(() => fake.recognition({ tur: "kismi", metin: "izin ver" }));
  act(() => fake.ask({ ...explicitAsk, questionId: "new", sessionId: "offline" }));
  vi.useFakeTimers();
  try {
    act(() => fake.recognition({ tur: "kismi", metin: "izin ver" }));
    await act(async () => { await vi.advanceTimersByTimeAsync(2600); });
    expect(fake.runtime.answerAsk).not.toHaveBeenCalled();
  } finally { vi.useRealTimers(); }
});

it("aynı soru yayını konuşma sahipliğini ve gönderim kilidini korur", async () => {
  localStorage.setItem("fusion.permission-explanations.v1", JSON.stringify({ microphone: true, speech: true }));
  const fake = fakeRuntime();
  const question = { ...ASK, sessionId: "offline", questionId: "same" };
  render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
  await startTalk();
  await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
  act(() => fake.ask(question));
  act(() => fake.recognition({ tur: "kismi", metin: "onayla" }));
  act(() => fake.ask({ ...question }));
  act(() => fake.recognition({ tur: "son", metin: "onayla" }));
  await waitFor(() => expect(fake.runtime.answerAsk).toHaveBeenCalledOnce());
  act(() => fake.ask({ ...question }));
  fireEvent.click(screen.getByRole("button", { name: "Sorunun tamamını oku" }));
  fireEvent.click(screen.getByRole("button", { name: "Onayla" }));
  expect(fake.runtime.answerAsk).toHaveBeenCalledOnce();
});

describe("VoiceWindow — uyandırma sınırı", () => {
  it("pencere açılınca mikrofon kapalıdır; karaktere basınca açılır, söz adsız doğrudan modele gider", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); });
    expect(fake.runtime.startRecognition).not.toHaveBeenCalled();
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    act(() => fake.recognition({ tur: "son", metin: "projeyi aç" }));
    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledWith({ kaynak: "kullanici", metin: "projeyi aç" }));
  });

  it("istek tam algılanıp gönderilince mikrofon kendiliğinden kapanır, cevap sonrası geri açılmaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    act(() => fake.recognition({ tur: "son", metin: "projeyi aç" }));
    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledOnce());
    await waitFor(() => expect(fake.runtime.stopRecognition).toHaveBeenCalled());
    expect(screen.getByRole("button", { name: /Mikrofon kapalı/ })).toBeTruthy();
    // Cevap gelir ve biter: dinleme kendiliğinden başlamaz.
    act(() => fake.runtimeState({ durum: "talking", metin: "Tamam." }));
    act(() => fake.runtimeState({ durum: "idle" }));
    await new Promise((resolve) => setTimeout(resolve, 900));
    expect(fake.runtime.startRecognition).toHaveBeenCalledOnce();
    // Yeni komut için karaktere yeniden basılır.
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2));
  });

  it("açıkken karaktere ikinci basış mikrofonu kapatır ve geri açmaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: /Mikrofon açık/ }));
    await waitFor(() => expect(fake.runtime.stopRecognition).toHaveBeenCalled());
    expect(fake.runtime.interruptSpeech).not.toHaveBeenCalled();
    act(() => fake.recognitionEnded());
    await new Promise((resolve) => setTimeout(resolve, 900));
    expect(fake.runtime.startRecognition).toHaveBeenCalledOnce();
    expect(screen.getByRole("button", { name: /Mikrofon kapalı/ })).toBeTruthy();
  });

  it("kimse konuşmazsa mikrofon kendiliğinden kapanır", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow idleCheckMs={20} idleEndMs={80} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    await waitFor(() => expect(fake.runtime.stopRecognition).toHaveBeenCalled(), { timeout: 4000 });
    expect(await screen.findByRole("button", { name: /Mikrofon kapalı/ })).toBeTruthy();
  });

  it("konuşma sürerken sessizlik süresi dolmaz (söz her seferinde süreyi tazeler)", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow idleCheckMs={20} idleEndMs={300} runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    for (let step = 0; step < 6; step += 1) {
      act(() => fake.recognition({ tur: "kismi", metin: "devam ediyorum", segment: step + 1 }));
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    expect(screen.getByRole("button", { name: /Mikrofon açık/ })).toBeTruthy();
  });

  it("model düşünürken kısa süre sonra üretilen 'hmm' sesini çalar, cevap başlayınca susar", async () => {
    const hum = vi.spyOn(cues, "playHum").mockImplementation(() => undefined);
    const stop = vi.spyOn(cues, "stopHum").mockImplementation(() => undefined);
    try {
      const fake = fakeRuntime();
      render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
      await startTalk();
      await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
      act(() => fake.recognition({ tur: "son", metin: "bu uzun bir iş olsun" }));
      await waitFor(() => expect(hum).toHaveBeenCalledOnce(), { timeout: 3000 });
      expect(screen.getByText("Hmm…")).toBeTruthy();
      act(() => fake.runtimeState({ durum: "talking", metin: "Cevap geldi." }));
      expect(stop).toHaveBeenCalled();
      expect(screen.queryByText("Hmm…")).toBeNull();
    } finally { hum.mockRestore(); stop.mockRestore(); }
  });

  it("Fusion konuşurken karaktere basmak sözünü keser, mikrofonu yeniden açmaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    act(() => fake.runtimeState({ durum: "talking", metin: "Uzun yanıt" }));
    fireEvent.click(screen.getByRole("button", { name: /Fusion/ }));
    await waitFor(() => expect(fake.runtime.interruptSpeech).toHaveBeenCalledOnce());
    expect(fake.runtime.startRecognition).toHaveBeenCalledOnce();
  });
});

it("Fusion sözü yerel Hm yanıtı üretir ve modele gönderilmez", async () => {
  const speak = vi.fn();
  vi.stubGlobal("speechSynthesis", { speak });
  vi.stubGlobal("SpeechSynthesisUtterance", class { text: string; constructor(text: string) { this.text = text; } });
  try {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    act(() => fake.recognition({ tur: "son", metin: "Fusion" }));
    await waitFor(() => expect(speak).toHaveBeenCalledOnce());
    expect(speak.mock.calls[0][0].text).toBe("Hm");
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
  } finally { vi.unstubAllGlobals(); }
});
it("Dikte kapalıysa otomatik yeniden deneme döngüsü durur", async () => {
  const fake = fakeRuntime();
  render(<VoiceWindow continuous runtime={fake.runtime} />);
  await startTalk();
  await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
  act(() => fake.recognition({ tur: "hata", metin: "Siri and Dictation are disabled" }));
  act(() => fake.recognitionEnded());
  expect(screen.getByRole("alert").textContent).toContain("Klavye → Dikte");
  await new Promise((resolve) => setTimeout(resolve, 900));
  expect(fake.runtime.startRecognition).toHaveBeenCalledOnce();
  fireEvent.click(screen.getByRole("button", { name: /Fusion.*dinle/i }));
  await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2));
});

it("arka plan sesi asistanı kesmez; Fusion öneki kesebilir", async () => {
  const fake = fakeRuntime();
  render(<VoiceWindow continuous runtime={fake.runtime} />);
  await startTalk();
  await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
  act(() => fake.runtimeState({ durum: "talking", metin: "Uzun yanıt" }));
  act(() => fake.recognition({ tur: "ses-basladi", metin: "" }));
  act(() => fake.recognition({ tur: "kismi", metin: "arka plan sesi" }));
  expect(fake.runtime.interruptSpeech).not.toHaveBeenCalled();
  act(() => fake.recognition({ tur: "kismi", metin: "Fusion dur" }));
  await waitFor(() => expect(fake.runtime.interruptSpeech).toHaveBeenCalledOnce());
  act(() => fake.recognition({ tur: "kismi", metin: "Fusion dur şimdi" }));
  act(() => fake.recognition({ tur: "son", metin: "Fusion dur şimdi" }));
  expect(fake.runtime.interruptSpeech).toHaveBeenCalledOnce();
});

it("aynı yerel mikrofon sürecinde farklı konuşma segmentlerini birer kez kabul eder", async () => {
  const fake = fakeRuntime();
  render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
  await startTalk();
  await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
  for (let segment = 1; segment <= 3; segment += 1) {
    act(() => fake.recognition({ tur: "son", metin: `mesaj ${segment}`, segment }));
    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledTimes(segment));
  }
  act(() => fake.recognition({ tur: "son", metin: "geç gelen ilk mesaj", segment: 1 }));
  expect(fake.runtime.emitMessage).toHaveBeenCalledTimes(3);
  expect(fake.runtime.startRecognition).toHaveBeenCalledOnce();
});

it("aynı süreçte sonraki tek partial da zaman aşımında gönderilir; eski partial onu silemez", async () => {
  const fake = fakeRuntime();
  render(<VoiceWindow continuous wakeEnabled={false} runtime={fake.runtime} />);
  await startTalk();
  await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
  act(() => fake.recognition({ tur: "son", metin: "ilk mesaj", segment: 1 }));
  await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledOnce());
  act(() => fake.recognition({ tur: "kismi", metin: "ikinci mesaj", segment: 2 }));
  act(() => fake.recognition({ tur: "kismi", metin: "geç gelen ilk mesaj", segment: 1 }));
  await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledWith({ kaynak: "kullanici", metin: "ikinci mesaj" }), { timeout: 4200 });
  expect(fake.runtime.emitMessage).toHaveBeenCalledTimes(2);
});

it("Füzyon kısmi tanıması son sonucu beklemeden bir kez Hm der", async () => {
  const speak = vi.fn();
  vi.stubGlobal("speechSynthesis", { speak });
  vi.stubGlobal("SpeechSynthesisUtterance", class { constructor(public text: string) {} });
  try {
    const fake = fakeRuntime();
    render(<VoiceWindow continuous runtime={fake.runtime} />);
    await startTalk();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    act(() => fake.recognition({ tur: "kismi", metin: "Füzyon" }));
    expect(speak).toHaveBeenCalledOnce();
    act(() => fake.recognition({ tur: "kismi", metin: "Füzyon" }));
    act(() => fake.recognition({ tur: "son", metin: "Füzyon" }));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(speak).toHaveBeenCalledOnce();
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
    act(() => fake.recognition({ tur: "kismi", metin: "Füzyon", segment: 2 }));
    expect(speak).toHaveBeenCalledTimes(2);
  } finally { vi.unstubAllGlobals(); }
});

it("hitaplı selamdan sonra sohbeti sürdürürken adı tekrar istemez", async () => {
 const fake=fakeRuntime(); render(<VoiceWindow continuous runtime={fake.runtime} />); await startTalk();
 await waitFor(()=>expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
 act(()=>fake.recognition({tur:"son",metin:"Merhaba Füzyon",segment:1}));
 await waitFor(()=>expect(fake.runtime.emitMessage).toHaveBeenCalledTimes(1));
 act(()=>fake.recognition({tur:"son",metin:"projeyi aç",segment:2}));
 await waitFor(()=>expect(fake.runtime.emitMessage).toHaveBeenCalledWith({kaynak:"kullanici",metin:"projeyi aç"}));
});
it("sohbet açıkken salt ses veya hmm asistanı kesmez", async()=>{
 const fake=fakeRuntime(); render(<VoiceWindow continuous runtime={fake.runtime} />); await startTalk();
 await waitFor(()=>expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
 // Sohbet açık: kullanıcının kabul edilmiş bir turu uyanık penceresini açar.
 act(()=>fake.recognition({tur:"son",metin:"Merhaba",segment:1}));
 await waitFor(()=>expect(fake.runtime.emitMessage).toHaveBeenCalledOnce());
 act(()=>fake.runtimeState({durum:"talking",metin:"Yanıtım sürüyor."}));
 act(()=>fake.recognition({tur:"ses-basladi",metin:"",segment:2}));
 act(()=>fake.recognition({tur:"kismi",metin:"hmm",segment:2}));
 expect(fake.runtime.interruptSpeech).not.toHaveBeenCalled();
 act(()=>fake.recognition({tur:"kismi",metin:"bir dakika",segment:2}));
 await waitFor(()=>expect(fake.runtime.interruptSpeech).toHaveBeenCalledOnce());
});

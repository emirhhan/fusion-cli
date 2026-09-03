import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { PermissionBridge } from "../permissions/types";
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

    expect(requested).toEqual([]);
    expect(fake.runtime.startRecognition).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: /Devam et/i }));
    await waitFor(() => expect(requested).toEqual(["microphone"]));
    fireEvent.click(screen.getByRole("button", { name: /Devam et/i }));

    await waitFor(() => expect(requested).toEqual(["microphone", "speech"]));
    expect(fake.runtime.preflightRecognition).toHaveBeenCalledOnce();
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
  });

  it("dört taze oturumu farklı metinlerle birer kez yollar, sessiz beşinci turu yollamaz", { timeout: 20_000 }, async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
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

  it("sessizlik kaynaklı düşük güvenli Evet tekrarını ne gösterir ne yollar", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fake.recognition({ tur: "kismi", metin: "Evet", guven: 0.08, speech_ms: 0 });
    await new Promise((resolve) => setTimeout(resolve, 1_500));

    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
    expect(screen.queryByText("Evet")).toBeNull();
  });

  it("reddedilen final sırasında etkin recognition sahipliğini durdurma eylemiyle gösterir", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fake.recognition({ tur: "son", metin: "belirsiz", guven: 0.1, speech_ms: 420 });
    await waitFor(() => expect(screen.getByRole("region", { name: "Fusion Talk" }).getAttribute("data-state")).toBe("interrupted"));

    // Sahiplik artık tuşla değil göstergeyle bildirilir.
    expect(screen.getByRole("status", { name: "Dinliyor" })).toBeTruthy();
    expect(fake.runtime.startRecognition).toHaveBeenCalledOnce();
  });
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

  it("Apple final vermese de duran kısmi metni hızlıca kesinleştirir", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);

    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.recognition({ tur: "kismi", metin: "merhaba fusion" });

    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledWith({
      kaynak: "kullanici",
      metin: "merhaba fusion",
    }), { timeout: 2_000 });
    expect(fake.runtime.stopRecognition).toHaveBeenCalledOnce();
  });

  it("kısa düşünme duraklamasında cümleyi erken kesmez", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
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
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(1));

    fake.runtimeState({ durum: "talking", metin: "Merhaba" });
    await screen.findByText("Konuşuyorum");
    expect(fake.runtime.stopRecognition).not.toHaveBeenCalled();

    fake.recognition({ tur: "ses-basladi", metin: "", guven: null, speech_ms: 80 });
    await waitFor(() => expect(fake.runtime.interruptSpeech).toHaveBeenCalledOnce());

    fake.runtimeState({ durum: "interrupted" });
    fake.runtimeState({ durum: "listening" });
    expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(1);
    await screen.findByText("Seni duyuyorum…");
  });

  it("barge-in tamponlarini TTS iptal onayindan once kabul etmez", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fake.runtimeState({ durum: "talking", metin: "Uzun yanit" });
    await screen.findByText("Konuşuyorum");
    fake.recognition({ tur: "ses-basladi", metin: "", guven: null, speech_ms: 80 });
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
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fake.recognition({ tur: "son", metin: "merhaba", guven: 0.95, speech_ms: 600 });

    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledWith({
      kaynak: "kullanici",
      metin: "merhaba",
    }));
  });

  it("TTS iptali basarisizsa eski tamponu atar ve taze retry konusmasini kabul eder", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
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
    render(<VoiceWindow runtime={fake.runtime} />);
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
    render(<VoiceWindow runtime={fake.runtime} />);
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
    render(<VoiceWindow runtime={fake.runtime} />);

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
    render(<VoiceWindow runtime={fake.runtime} />);

    await waitFor(() => expect(fake.runtime.preflightRecognition).toHaveBeenCalledOnce());
    // Talk kapanınca bekleyen izin denetimi eski isteği başlatmamalı.
    cleanup();
    resolvePreflight?.(true);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(fake.runtime.startRecognition).not.toHaveBeenCalled();
  });

  it("aynı oturumun farklı ikinci finalini sohbete ikinci kez yollamaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fake.recognition({ tur: "son", metin: "ilk" });
    fake.recognition({ tur: "son", metin: "ikinci" });

    await waitFor(() => expect(fake.runtime.emitMessage).toHaveBeenCalledOnce());
    expect(fake.runtime.emitMessage).toHaveBeenCalledWith({ kaynak: "kullanici", metin: "ilk" });
  });

  it("eski oturum çıktısını ve bitişini yeni oturuma karıştırmaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
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

  it("mini ve normal görünüm geçişinde recognition sürecini kesmez", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());

    fireEvent.click(screen.getByRole("button", { name: "Paneli küçült" }));
    fireEvent.click(screen.getByRole("button", { name: "Paneli büyüt" }));

    expect(fake.runtime.stopRecognition).not.toHaveBeenCalled();
    expect(fake.runtime.startRecognition).toHaveBeenCalledOnce();
  });

  it("izin verilmezse sureci baslatmaz ve kendiliginden tekrar dener", async () => {
    const fake = fakeRuntime();
    vi.mocked(fake.runtime.preflightRecognition)
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);
    render(<VoiceWindow runtime={fake.runtime} />);

    expect(await screen.findByText("Mikrofon izni verilmedi. İzin verdikten sonra yeniden deneyin.")).toBeTruthy();
    expect(fake.runtime.startRecognition).not.toHaveBeenCalled();
    // Basılacak tuş yok: izin verildikten sonra uygulama kendi yeniden dener.
    fake.recognitionEnded("izin sonrası", 0);
    await waitFor(
      () => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce(),
      { timeout: 3_000 },
    );
  });

  it("beklenmedik cikistan sonra dinleme kendiliginden toparlanir", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
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
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.recognitionEnded("Yardımcı beklenmedik kapandı");
    expect(await screen.findByText("Yardımcı beklenmedik kapandı")).toBeTruthy();
    expect(screen.getByText("Bir sorun oluştu")).toBeTruthy();
  });

  it("normal TTS bitisinde dusuk gecikmeli VAD oturumunu yeniden baslatmaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
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
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(1));
    fake.ask(ASK);
    expect(await screen.findByRole("group", { name: "Onay" })).toBeTruthy();

    fake.recognition({ tur: "son", metin: "onayla" });
    await waitFor(() => expect(fake.runtime.answerAsk).toHaveBeenCalledWith("evet"));
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
  });

  it("aynı turdaki ikinci finalin onayı iki kez çalıştırmasını engeller", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.ask(ASK);
    await screen.findByRole("group", { name: "Onay" });

    fake.recognition({ tur: "son", metin: "onayla" });
    fake.recognition({ tur: "son", metin: "onayla" });

    await waitFor(() => expect(fake.runtime.answerAsk).toHaveBeenCalledOnce());
    expect(fake.runtime.answerAsk).toHaveBeenCalledWith("evet");
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

  it("eski belirsiz onayın yeniden başlatma niyetini yeni oturum sonuna taşımaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
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
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.ask(ASK);

    fake.recognition({ tur: "kismi", metin: "olabilir ama emin değilim" });

    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2), { timeout: 2_000 });
    expect(fake.runtime.answerAsk).not.toHaveBeenCalled();
    expect(fake.runtime.emitMessage).not.toHaveBeenCalled();
    expect(screen.getByRole("group", { name: "Onay" })).toBeTruthy();
  });

  it("önceki kısmi eveti sonradan açılan onaya uygulamaz", async () => {
    const fake = fakeRuntime();
    render(<VoiceWindow runtime={fake.runtime} />);
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
    render(<VoiceWindow runtime={fake.runtime} />);
    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledOnce());
    fake.ask(ASK);

    fake.recognition({ tur: "kismi", metin: "olabilir ama emin değilim" });

    await waitFor(() => expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2), { timeout: 2_000 });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fake.runtime.startRecognition).toHaveBeenCalledTimes(2);
  });
});

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KitsScreen } from "./KitsScreen";
import { kitsFrameUrl } from "./kitsUrl";

afterEach(cleanup);

describe("kitsFrameUrl", () => {
  it("dosya köprüsü yalnız yeni host açıkça sunduğunda ilan edilir", () => {
    expect(new URL(kitsFrameUrl("http://127.0.0.1:51234", "light", true)).searchParams.get("asset_protocol")).toBe("1");
  });
  it("yerel servis adresine yalnız yüzey işaretini ekler", () => {
    expect(kitsFrameUrl("http://127.0.0.1:51234")).toBe("http://127.0.0.1:51234/?surface=kits&theme=light");
  });

  it("temayı adrese ekler", () => {
    expect(kitsFrameUrl("http://127.0.0.1:51234", "dark")).toBe("http://127.0.0.1:51234/?surface=kits&theme=dark");
  });

  it("uzak adresi, kimlik bilgisini ve sorguyu reddeder", () => {
    expect(() => kitsFrameUrl("http://example.com:4410")).toThrow();
    expect(() => kitsFrameUrl("https://127.0.0.1:4410")).toThrow();
    expect(() => kitsFrameUrl("http://kullanici:parola@127.0.0.1:4410")).toThrow();
    expect(() => kitsFrameUrl("http://127.0.0.1:4410/?token=gizli")).toThrow();
  });
});

describe("KitsScreen", () => {
  it("Kit'in Chrome isteği hosta bağlanır: tarif oturumdan alınır, ret iframe'e 'denied' döner", async () => {
    // Ölçüldü (31 Ekim, inceleme): KitsBrowserHost'un KitsScreen'de gerçekten kurulduğu test edilmiyordu.
    const requestHost = vi.fn(async (name: string) =>
      name === "chrome.kit_tarif" ? { ok: true, status: "ok", hedef: "Gönder", riskli: true } : { ok: true, status: "ok", text: "{}" },
    );
    const confirmBrowser = vi.fn(async () => false);
    render(<KitsScreen start={() => Promise.resolve({ url: "http://127.0.0.1:50030" })} requestHost={requestHost} confirmBrowser={confirmBrowser} />);
    const frame = (await screen.findByTitle("Fusion Kits")) as HTMLIFrameElement;
    // Köprü, iframe'in jsdom penceresine bağlanır; yanıt oraya postMessage ile gider.
    const inner = frame.contentWindow!;
    expect(inner).toBeTruthy();
    const post = vi.spyOn(inner, "postMessage").mockImplementation(() => {});
    window.dispatchEvent(new MessageEvent("message", {
      data: { type: "fusion-browser-request", nonce: "n1", input: { action: "click", ref: "e3" }, kit: { id: "k1", name: "Kod" } },
      origin: "http://127.0.0.1:50030",
      source: inner,
    }));
    await vi.waitFor(() => expect(post).toHaveBeenCalledWith(
      expect.objectContaining({ type: "fusion-browser-result", nonce: "n1", status: "denied" }),
      "http://127.0.0.1:50030",
    ), { timeout: 5_000 });
    expect(requestHost).toHaveBeenCalledWith("chrome.kit_tarif", { action: "click", ref: "e3" });
    expect(confirmBrowser).toHaveBeenCalledWith(expect.stringContaining("«Kod» Kit'i Chrome'unda «Gönder» öğesine tıklamak"), true, true);
    expect(requestHost).not.toHaveBeenCalledWith("chrome.kit_komut", expect.anything());
    post.mockRestore();
  });

  it("yan süreç hazır olunca modülü iframe ile gömer", async () => {
    render(<KitsScreen start={() => Promise.resolve({ url: "http://127.0.0.1:50001" })} statusDelayMs={0} />);
    expect(screen.getByText("Kits başlatılıyor…")).toBeTruthy();
    const frame = await screen.findByTitle("Fusion Kits");
    expect(frame.getAttribute("src")).toBe("http://127.0.0.1:50001/?surface=kits&theme=light&asset_protocol=1");
    expect(frame.getAttribute("referrerpolicy")).toBe("no-referrer");
  });

  it("ön başlatılmış Kits'te durum metni yanıp sönmez; başlatma uzarsa sebebi söylenir", async () => {
    // Ölçüldü (31 Ekim): ön başlatmayla `kits_baslat` birkaç ms'de döner; metin bir kare görünüp kayboluyordu.
    vi.useFakeTimers();
    try {
      render(<KitsScreen start={() => new Promise(() => {})} statusDelayMs={300} slowHintMs={4_000} />);
      expect(screen.getByRole("status").getAttribute("aria-busy")).toBe("true");
      expect(screen.queryByText("Kits başlatılıyor…")).toBeNull();
      await act(async () => { vi.advanceTimersByTime(300); });
      expect(screen.getByText("Kits başlatılıyor…")).toBeTruthy();
      expect(screen.queryByText(/birkaç saniye/)).toBeNull();
      await act(async () => { vi.advanceTimersByTime(3_700); });
      expect(screen.getByText(/birkaç saniye sürebilir/)).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  it("başlatma hatasını gösterir ve yeniden denemeye izin verir", async () => {
    const start = vi
      .fn<() => Promise<{ url: string }>>()
      .mockRejectedValueOnce("Node.js 24 veya üzeri bulunamadı.")
      .mockResolvedValueOnce({ url: "http://127.0.0.1:50002" });
    render(<KitsScreen start={start} />);
    expect((await screen.findByRole("alert")).textContent).toBe("Node.js 24 veya üzeri bulunamadı.");
    fireEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));
    expect(await screen.findByTitle("Fusion Kits")).toBeTruthy();
    expect(start).toHaveBeenCalledTimes(2);
  });

  it("Fusion koyu temadaysa Kits koyu açılır ve tema değişimi sayfayı yenilemeden iletilir", async () => {
    document.documentElement.dataset.theme = "dark";
    render(<KitsScreen start={() => Promise.resolve({ url: "http://127.0.0.1:50003" })} />);
    const frame = (await screen.findByTitle("Fusion Kits")) as HTMLIFrameElement;
    expect(frame.getAttribute("src")).toBe("http://127.0.0.1:50003/?surface=kits&theme=dark&asset_protocol=1");
    const post = vi.fn();
    Object.defineProperty(frame, "contentWindow", { configurable: true, value: { postMessage: post } });
    delete document.documentElement.dataset.theme;
    await vi.waitFor(() => expect(post).toHaveBeenCalledWith(
      { type: "fusion-kits-theme", theme: "light" }, "http://127.0.0.1:50003",
    ));
    expect(frame.getAttribute("src")).toContain("theme=dark");
  });

  it("Kits süreci yeni portta yeniden başlarsa iframe yeni adrese taşınır", async () => {
    const start = vi
      .fn<() => Promise<{ url: string }>>()
      .mockResolvedValueOnce({ url: "http://127.0.0.1:50010" })
      .mockResolvedValueOnce({ url: "http://127.0.0.1:50010" })
      .mockResolvedValue({ url: "http://127.0.0.1:50011" });
    render(<KitsScreen start={start} watchIntervalMs={10} />);
    const frame = await screen.findByTitle("Fusion Kits");
    expect(frame.getAttribute("src")).toContain(":50010/");
    await vi.waitFor(() =>
      expect(screen.getByTitle("Fusion Kits").getAttribute("src")).toContain(":50011/"),
    );
  });

  it("yoklama geçici olarak başarısız olursa iframe yerinde kalır", async () => {
    const start = vi
      .fn<() => Promise<{ url: string }>>()
      .mockResolvedValueOnce({ url: "http://127.0.0.1:50020" })
      .mockRejectedValue("Kits sunucusu başlatılamadı");
    render(<KitsScreen start={start} watchIntervalMs={10} />);
    await screen.findByTitle("Fusion Kits");
    await vi.waitFor(() => expect(start.mock.calls.length).toBeGreaterThan(2));
    expect(screen.getByTitle("Fusion Kits").getAttribute("src")).toContain(":50020/");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("güvensiz adres dönerse iframe kurmaz", async () => {
    render(<KitsScreen start={() => Promise.resolve({ url: "http://example.com" })} />);
    expect((await screen.findByRole("alert")).textContent).toContain("yerel");
    expect(screen.queryByTitle("Fusion Kits")).toBeNull();
  });

  it("bölüm gizliyken adres yoklaması durur, görününce sürer (U6-16a)", async () => {
    // Ölçüldü (30 Ekim): gizli Kits'te de her aralıkta `kits_baslat` invoke ediliyordu.
    const start = vi.fn<() => Promise<{ url: string }>>().mockResolvedValue({ url: "http://127.0.0.1:50030" });
    const { rerender } = render(<KitsScreen start={start} visible={false} watchIntervalMs={10} />);
    await screen.findByTitle("Fusion Kits");
    await new Promise((resolve) => setTimeout(resolve, 80));
    expect(start).toHaveBeenCalledTimes(1);
    rerender(<KitsScreen start={start} visible watchIntervalMs={10} />);
    await vi.waitFor(() => expect(start.mock.calls.length).toBeGreaterThan(2));
  });

  it("üst bileşen satır içi işlev verse de teslimat istemcisi yeniden kurulmaz (U6-16c)", async () => {
    const start = () => Promise.resolve({ url: "http://127.0.0.1:50031" });
    const ilk = vi.fn();
    const ikinci = vi.fn();
    const { rerender } = render(<KitsScreen onDeliveryClient={ilk} start={start} />);
    await screen.findByTitle("Fusion Kits");
    await vi.waitFor(() => expect(ilk).toHaveBeenCalledTimes(1));
    rerender(<KitsScreen onDeliveryClient={ikinci} start={start} />);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(ilk).toHaveBeenCalledTimes(1);
    expect(ilk).not.toHaveBeenCalledWith(null);
    expect(ikinci).not.toHaveBeenCalled();
  });

  it("Kits'teki zamanlanmış görev onay isterse üst bileşene haber verir (U5-57)", async () => {
    const onScheduleApproval = vi.fn();
    render(<KitsScreen onScheduleApproval={onScheduleApproval} start={() => Promise.resolve({ url: "http://127.0.0.1:50032" })} />);
    const frame = (await screen.findByTitle("Fusion Kits")) as HTMLIFrameElement;
    const occurrenceId = "c".repeat(64);
    const message = { type: "fusion-schedule-approval", occurrenceId, taskId: `schedule-${occurrenceId}`, tool: "run_shell" };
    // Yabancı pencereden gelen bildirim sayılmaz.
    window.dispatchEvent(new MessageEvent("message", { data: message, origin: "http://127.0.0.1:50032", source: window }));
    expect(onScheduleApproval).not.toHaveBeenCalled();

    window.dispatchEvent(new MessageEvent("message", { data: message, origin: "http://127.0.0.1:50032", source: frame.contentWindow }));

    expect(onScheduleApproval).toHaveBeenCalledWith({ occurrenceId, taskId: `schedule-${occurrenceId}`, title: "Zamanlanmış görev", tool: "run_shell" });
  });
});

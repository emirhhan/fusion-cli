import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
  it("yan süreç hazır olunca modülü iframe ile gömer", async () => {
    render(<KitsScreen start={() => Promise.resolve({ url: "http://127.0.0.1:50001" })} />);
    expect(screen.getByText("Kits hazırlanıyor…")).toBeTruthy();
    const frame = await screen.findByTitle("Fusion Kits");
    expect(frame.getAttribute("src")).toBe("http://127.0.0.1:50001/?surface=kits&theme=light&asset_protocol=1");
    expect(frame.getAttribute("referrerpolicy")).toBe("no-referrer");
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
});

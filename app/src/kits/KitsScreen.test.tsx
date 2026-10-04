import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KitsScreen } from "./KitsScreen";
import { kitsFrameUrl } from "./kitsUrl";

afterEach(cleanup);

describe("kitsFrameUrl", () => {
  it("yerel servis adresine yalnız yüzey işaretini ekler", () => {
    expect(kitsFrameUrl("http://127.0.0.1:51234")).toBe("http://127.0.0.1:51234/?surface=kits");
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
    expect(frame.getAttribute("src")).toBe("http://127.0.0.1:50001/?surface=kits");
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

  it("güvensiz adres dönerse iframe kurmaz", async () => {
    render(<KitsScreen start={() => Promise.resolve({ url: "http://example.com" })} />);
    expect((await screen.findByRole("alert")).textContent).toContain("yerel");
    expect(screen.queryByTitle("Fusion Kits")).toBeNull();
  });
});

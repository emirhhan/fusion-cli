import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { Intelligence } from "./Intelligence";

afterEach(cleanup);

function baseStatus(over: Record<string, unknown> = {}) {
  return {
    ok: true,
    motor: "agent",
    motorlar: [
      { deger: "agent", etiket: "Tek ajan" },
      { deger: "fusion", etiket: "Fusion" },
    ],
    planKipi: "off",
    planKipleri: [
      { deger: "off", etiket: "Tek döngü" },
      { deger: "always", etiket: "Plan motoru" },
    ],
    ogretmenTanimli: false,
    bayraklar: [
      { anahtar: "lessons", etiket: "Kendini geliştirme", aciklama: "Ders çıkarır.", maliyet: "1 çağrı", grup: "Öğrenme", acik: true },
      { anahtar: "teacherless", etiket: "Öğretmene danış", aciklama: "Öğretmen.", maliyet: "ek çağrı", grup: "Öğrenme", acik: true },
      { anahtar: "visual_verification", etiket: "Görsel doğrulama", aciklama: "Görme modeli.", maliyet: "pahalı", grup: "Doğrulama", acik: false },
    ],
    ...over,
  };
}

function fakeClient() {
  let current = baseStatus();
  return {
    request: vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "zeka.durum") return current;
      if (name === "zeka.ayarla") {
        if (data.anahtar === "motor") current = baseStatus({ motor: data.deger });
        if (data.anahtar === "planKipi") current = baseStatus({ planKipi: data.deger });
        if (data.anahtar === "visual_verification") {
          current = baseStatus({
            bayraklar: current.bayraklar.map((flag) =>
              flag.anahtar === data.anahtar ? { ...flag, acik: data.deger } : flag,
            ),
          });
        }
        return current;
      }
      return { ok: false, metin: "bilinmiyor" };
    }),
  } as unknown as ProtocolClient;
}

describe("Intelligence", () => {
  it("motorları, plan kipini ve her anahtarı açıklama ve maliyetle gösterir", async () => {
    render(<Intelligence client={fakeClient()} />);
    expect(await screen.findByText("Tek ajan")).toBeTruthy();
    expect(screen.getByText("Plan motoru")).toBeTruthy();
    expect(screen.getByText("Ders çıkarır.")).toBeTruthy();
    expect(screen.getByText("Maliyet: pahalı")).toBeTruthy();
    expect(screen.getByText(/Öğretmen modeli tanımlı değil/)).toBeTruthy();
  });

  it("anahtar değişince çekirdeğe yazar ve güncel durumu yansıtır", async () => {
    const client = fakeClient();
    render(<Intelligence client={client} />);
    const toggle = (await screen.findByLabelText("Görsel doğrulama")) as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    fireEvent.click(toggle);
    await waitFor(() =>
      expect(client.request).toHaveBeenCalledWith("zeka.ayarla", { anahtar: "visual_verification", deger: true }),
    );
    await waitFor(() => expect((screen.getByLabelText("Görsel doğrulama") as HTMLInputElement).checked).toBe(true));
  });

  it("motoru ve plan kipini seçer", async () => {
    const client = fakeClient();
    render(<Intelligence client={client} />);
    fireEvent.click(await screen.findByLabelText("Fusion"));
    await waitFor(() => expect(client.request).toHaveBeenCalledWith("zeka.ayarla", { anahtar: "motor", deger: "fusion" }));
    fireEvent.click(screen.getByLabelText("Plan motoru"));
    await waitFor(() => expect(client.request).toHaveBeenCalledWith("zeka.ayarla", { anahtar: "planKipi", deger: "always" }));
  });

  it("çekirdek reddederse hatayı gösterir", async () => {
    const client = {
      request: vi.fn(async (name: string) =>
        name === "zeka.durum" ? baseStatus() : { ok: false, metin: "Çalışan görevi durdur." },
      ),
    } as unknown as ProtocolClient;
    render(<Intelligence client={client} />);
    fireEvent.click(await screen.findByLabelText("Kendini geliştirme"));
    expect((await screen.findByRole("alert")).textContent).toContain("Çalışan görevi durdur.");
  });
});

describe("Intelligence — kalıcılık", () => {
  it("ayarı değiştirip ekrandan çıkıp girince seçimler durur", async () => {
    const client = fakeClient();
    const first = render(<Intelligence client={client as unknown as ProtocolClient} />);
    fireEvent.click(await screen.findByLabelText("Fusion"));
    await waitFor(() => expect(client.request).toHaveBeenCalledWith("zeka.ayarla", { anahtar: "motor", deger: "fusion" }));
    first.unmount();
    render(<Intelligence client={client as unknown as ProtocolClient} />);
    await waitFor(() => expect((screen.getByLabelText("Fusion") as HTMLInputElement).checked).toBe(true));
  });
});

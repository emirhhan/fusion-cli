import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { RemoteAccess } from "./RemoteAccess";

afterEach(cleanup);

function fakeClient(over: Record<string, Record<string, unknown>> = {}) {
  return {
    request: vi.fn(async (name: string) => ({
      ok: true,
      dinliyor: false,
      adres: "",
      telegram: false,
      telegramHata: "",
      cihazSayisi: 0,
      port: 8791,
      agAdresleri: [],
      cihazlar: [],
      sorular: [],
      kod: "ABCD2345",
      ...over[name],
    })),
  } as unknown as ProtocolClient;
}

it("yüksek yetkiler varsayılan kapalıdır ve kod yalnız seçilen kapsamlarla istenir", async () => {
  const client = fakeClient();
  render(<RemoteAccess client={client} />);
  const control = await screen.findByLabelText(/Masaüstünü kontrol etme/);
  expect((control as HTMLInputElement).checked).toBe(false);
  fireEvent.click(await screen.findByRole("button", { name: "Telefon için eşleştirme kodu oluştur" }));
  expect(await screen.findByText("ABCD2345")).toBeTruthy();
  expect(client.request).toHaveBeenCalledWith("uzak.eslestir_baslat", {
    kanal: "pwa",
    kapsamlar: ["project.read", "agent.run", "agent.cancel"],
  });
});

it("step-up onayını masaüstünde verir; uzaktaki soru için düğme göstermez", async () => {
  const client = fakeClient({
    "uzak.bekleyen": {
      sorular: [
        { soruId: "q1", runId: "r", baslik: "Tıkla", hedef: "Kaydet", onay: true },
        { soruId: "q2", runId: "r", baslik: "Hangi dal?", hedef: "", onay: false },
      ],
    },
  });
  render(<RemoteAccess client={client} />);
  fireEvent.click(await screen.findByRole("button", { name: "Bir kez izin ver" }));
  await waitFor(() =>
    expect(client.request).toHaveBeenCalledWith("uzak.onay_cevapla", { soruId: "q1", secim: "once" }),
  );
  expect(screen.getAllByRole("button", { name: "Bir kez izin ver" }).length).toBe(1);
});

it("cihaz erişimi iptal edilir ve Telegram belirteci parola alanında tutulur", async () => {
  const client = fakeClient({
    "uzak.cihazlar": {
      cihazlar: [{ deviceId: "dev_1", name: "Telefon", channel: "signed", scopes: [], revoked: false }],
    },
  });
  render(<RemoteAccess client={client} />);
  fireEvent.click(await screen.findByRole("button", { name: "Erişimi iptal et" }));
  await waitFor(() => expect(client.request).toHaveBeenCalledWith("uzak.cihaz_iptal", { cihazId: "dev_1" }));
  const token = screen.getByLabelText(/Bot belirteci/) as HTMLInputElement;
  expect(token.type).toBe("password");
});

it("tünel modunda yerel dinleme güvenilir tünel bayrağıyla başlar ve komutu gösterir", async () => {
  const client = fakeClient();
  render(<RemoteAccess client={client} />);
  expect(await screen.findByText(/tailscale serve --bg --https=443 http:\/\/127\.0\.0\.1:8791/)).toBeTruthy();
  fireEvent.click(await screen.findByRole("button", { name: "Dinlemeyi başlat" }));
  await waitFor(() =>
    expect(client.request).toHaveBeenCalledWith("uzak.baslat", { port: 8791, guvenilirTunel: true }),
  );
});

it("yerel ağ modu adres, sertifika ve anahtar olmadan başlatılamaz", async () => {
  const client = fakeClient({ "uzak.durum": { agAdresleri: ["192.168.1.20"] } });
  render(<RemoteAccess client={client} />);
  fireEvent.click(await screen.findByLabelText(/Yerel ağ \(Wi‑Fi\)/));
  const start = await screen.findByRole("button", { name: "Dinlemeyi başlat" });
  expect((start as HTMLButtonElement).disabled).toBe(true);
  fireEvent.change(await screen.findByLabelText("Bu bilgisayarın yerel ağ adresi"), { target: { value: "192.168.1.20" } });
  fireEvent.change(screen.getByLabelText("Sertifika dosyası (.pem)"), { target: { value: "/c.pem" } });
  fireEvent.change(screen.getByLabelText("Anahtar dosyası (.pem)"), { target: { value: "/k.pem" } });
  expect((start as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(start);
  await waitFor(() =>
    expect(client.request).toHaveBeenCalledWith("uzak.baslat", {
      port: 8791, adres: "192.168.1.20", yerelAg: true, sertifika: "/c.pem", anahtar: "/k.pem",
    }),
  );
});

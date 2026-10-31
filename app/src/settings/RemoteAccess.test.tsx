import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { RemoteAccess, approvalTrustLabel } from "./RemoteAccess";
import { REMOTE_SCOPES_KEY } from "./remotePreferences";

beforeEach(() => window.localStorage.clear());
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

it("ekran isteği masaüstünde onaylanır ve etkin paylaşım kesilebilir", async () => {
  const client = fakeClient({
    "uzak.ekran_bekleyen": {
      bekleyen: [{ cihazId: "dev_1", ad: "Telefonum" }],
      etkin: [{ cihazId: "dev_2", ad: "iPad" }],
    },
  });
  render(<RemoteAccess client={client} />);
  fireEvent.click(await screen.findByRole("button", { name: "Ekranı göstermeye izin ver" }));
  await waitFor(() => expect(client.request).toHaveBeenCalledWith("uzak.ekran_onayla", { cihazId: "dev_1" }));
  fireEvent.click(await screen.findByRole("button", { name: "Paylaşımı kes" }));
  await waitFor(() => expect(client.request).toHaveBeenCalledWith("uzak.ekran_kes", { cihazId: "dev_2" }));
  expect(screen.getByLabelText(/Ekranı görme/)).toBeTruthy();
});

it("seçilen kapsamları yeniden açılışta korur ve yalnız sonraki eşleştirmeye uygular", async () => {
  const client = fakeClient();
  const view = render(<RemoteAccess client={client} />);
  fireEvent.click(screen.getByLabelText(/Masaüstünü kontrol etme/));
  view.unmount();
  render(<RemoteAccess client={client} />);
  expect((screen.getByLabelText(/Masaüstünü kontrol etme/) as HTMLInputElement).checked).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Telefon için eşleştirme kodu oluştur" }));
  await waitFor(() => expect(client.request).toHaveBeenCalledWith("uzak.eslestir_baslat", {
    kanal: "pwa", kapsamlar: ["project.read", "agent.run", "agent.cancel", "desktop.control"],
  }));
  expect(vi.mocked(client.request).mock.calls.every(([name]) => ["uzak.durum", "uzak.cihazlar", "uzak.bekleyen", "uzak.ekran_bekleyen", "uzak.eslestir_baslat", "uzak.ayar"].includes(name))).toBe(true);
  expect(client.request).toHaveBeenCalledWith("uzak.ayar", { onayIste: true });
});

it.each(["{", "null", '{"version":2,"scopes":["desktop.control"]}', '{"version":1,"scopes":"desktop.control"}'])("bozuk kayıtla ek kapsamları kapalı açar: %s", (stored) => {
  window.localStorage.setItem(REMOTE_SCOPES_KEY, stored);
  render(<RemoteAccess client={fakeClient()} />);
  expect((screen.getByLabelText(/Masaüstünü kontrol etme/) as HTMLInputElement).checked).toBe(false);
});

it("kayıtlı kapsamları doğrular ve yalnız kapsam tercihini saklar", () => {
  window.localStorage.setItem(REMOTE_SCOPES_KEY, JSON.stringify({ version: 1, scopes: ["desktop.observe", "unknown", "desktop.observe", 7] }));
  render(<RemoteAccess client={fakeClient()} />);
  expect((screen.getByLabelText(/Ekranı görme/) as HTMLInputElement).checked).toBe(true);
  fireEvent.change(screen.getByLabelText(/Bot belirteci/), { target: { value: "deneme-belirteci" } });
  fireEvent.click(screen.getByLabelText(/Proje dosyalarını değiştirme/));
  expect(JSON.parse(window.localStorage.getItem(REMOTE_SCOPES_KEY)!)).toEqual({ version: 1, scopes: ["desktop.observe", "project.write"] });
});

it("onay iste anahtarı varsayılan kapalıdır ve çekirdeğe yazılır", async () => {
  const client = fakeClient();
  render(<RemoteAccess client={client} />);
  const toggle = (await screen.findByLabelText("Kodla eşleştirmede masaüstü onayı iste")) as HTMLInputElement;
  expect(toggle.checked).toBe(false);
  fireEvent.click(toggle);
  await waitFor(() => expect(client.request).toHaveBeenCalledWith("uzak.ayar", { onayIste: true }));
});

it("yeni cihaz eşleşince masaüstünde 'bağlandı' bildirimi gösterir", async () => {
  let status: Record<string, unknown> = { sonEslesen: null };
  const client = {
    request: vi.fn(async (name: string) => ({
      ok: true, dinliyor: false, adres: "", telegram: false, telegramHata: "", cihazSayisi: 0, port: 8791,
      agAdresleri: [], cihazlar: [], sorular: [], kod: "ABCD2345", ...(name === "uzak.durum" ? status : {}),
    })),
  } as unknown as ProtocolClient;
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    render(<RemoteAccess client={client} />);
    await screen.findByLabelText("Kodla eşleştirmede masaüstü onayı iste");
    status = { sonEslesen: { cihazId: "d1", ad: "Telefonum", zaman: 5 } };
    await act(async () => { await vi.advanceTimersByTimeAsync(4100); });
    expect(await screen.findByText("Telefonum bağlandı.")).toBeTruthy();
  } finally {
    vi.useRealTimers();
  }
});

import { parsePort } from "./RemoteAccess";
import { serveCommand } from "./RemoteGuide";

it("port 1-65535 tam sayı olmalı; geçersizse çekirdeğe gitmeden hata (U2-42)", async () => {
  expect(parsePort("8791")).toBe(8791);
  for (const bad of ["", " ", "abc", "0", "65536", "80; rm -rf /", "-1", "8791.5"]) expect(parsePort(bad)).toBeNull();
  const client = fakeClient();
  render(<RemoteAccess client={client} />);
  const port = await screen.findByLabelText("Port");
  fireEvent.change(port, { target: { value: "abc" } });
  fireEvent.click(screen.getByRole("button", { name: "Dinlemeyi başlat" }));
  expect((await screen.findByRole("alert")).textContent).toContain("1 ile 65535");
  expect(vi.mocked(client.request).mock.calls.some(([name]) => name === "uzak.baslat")).toBe(false);
});

it("kabuk komutuna yalnız rakam portu gömülür (U2-42)", () => {
  expect(serveCommand("8791")).toContain("http://127.0.0.1:8791");
  expect(serveCommand("80; rm -rf /")).toContain("http://127.0.0.1:8791");
  expect(serveCommand("")).toContain("http://127.0.0.1:8791");
});

it("yoklama hatası sonraki başarılı yoklamada kalkar ve yoklamalar üst üste binmez (U2-41)", async () => {
  vi.useFakeTimers();
  try {
    let durumCagrisi = 0;
    const client = {
      request: vi.fn(async (name: string) => {
        if (name === "uzak.durum") {
          durumCagrisi += 1;
          if (durumCagrisi === 1) throw new Error("çekirdek meşgul");
        }
        return { ok: true, dinliyor: false, adres: "", telegram: false, telegramHata: "", cihazSayisi: 0, port: 8791, agAdresleri: [], cihazlar: [], sorular: [] };
      }),
    } as unknown as ProtocolClient;
    render(<RemoteAccess client={client} />);
    await act(async () => { await act(async () => { await vi.advanceTimersByTimeAsync(0); }); });
    expect(screen.getByRole("alert").textContent).toContain("çekirdek meşgul");
    await act(async () => { await vi.advanceTimersByTimeAsync(4000); });
    expect(screen.queryByRole("alert")).toBeNull();
  } finally { vi.useRealTimers(); }
});

it("masaüstü kontrolü ya da üretime yayın seçiliyken onay anahtarı açık ve kilitlidir; seçim çekirdeğe yazılır (U2-43)", async () => {
  const client = fakeClient();
  render(<RemoteAccess client={client} />);
  const onay = (await screen.findByLabelText(/Kodla eşleştirmede masaüstü onayı iste/)) as HTMLInputElement;
  expect(onay.checked).toBe(false);
  fireEvent.click(await screen.findByLabelText(/Üretime yayın/));
  await waitFor(() => expect(client.request).toHaveBeenCalledWith("uzak.ayar", { onayIste: true }));
  expect(screen.getAllByText("Her eşleştirme masaüstünde elle onaylanır").length).toBe(2);
  const kilitli = (await screen.findByLabelText(/Kodla eşleştirmede masaüstü onayı iste/)) as HTMLInputElement;
  expect(kilitli.checked).toBe(true);
  expect(kilitli.getAttribute("aria-disabled")).toBe("true");
  vi.mocked(client.request).mockClear();
  fireEvent.click(kilitli);
  expect(client.request).not.toHaveBeenCalledWith("uzak.ayar", { onayIste: false });
});

it("yüksek yetkili kodda 'kendiliğinden bağlanır' denmez; çekirdeğin elle onay uyarısı gösterilir (U2-43)", async () => {
  const client = fakeClient({ "uzak.eslestir_baslat": { yuksekYetki: ["project.write"] } });
  render(<RemoteAccess client={client} />);
  fireEvent.click(await screen.findByLabelText(/Proje dosyalarını değiştirme/));
  fireEvent.click(await screen.findByRole("button", { name: "Telefon için eşleştirme kodu oluştur" }));
  expect(await screen.findByText("Cihaz kodu girdikten sonra onayla.")).toBeTruthy();
  expect(screen.queryByText(/kendiliğinden bağlanır/)).toBeNull();
});

it("uzaktan onay için süreli yetki şartı açılır ve cihaza yetki verilir/kaldırılır (P-040)", async () => {
  const simdi = Date.now() / 1000;
  const client = fakeClient({
    "uzak.cihazlar": {
      cihazlar: [
        { deviceId: "dev_1", name: "Telefon", channel: "signed", scopes: [], revoked: false, approvalTrustedUntil: 0 },
        { deviceId: "dev_2", name: "Tablet", channel: "signed", scopes: [], revoked: false, approvalTrustedUntil: simdi + 2 * 3600 },
      ],
    },
  });
  render(<RemoteAccess client={client} />);
  fireEvent.click(await screen.findByLabelText("Uzaktan onay için cihaz başına süreli yetki iste"));
  await waitFor(() => expect(client.request).toHaveBeenCalledWith("uzak.ayar", { onayYetkisiIste: true }));
  fireEvent.click(await screen.findByRole("button", { name: "Onay yetkisi ver (18 sa)" }));
  await waitFor(() => expect(client.request).toHaveBeenCalledWith("uzak.onay_yetkisi", { cihazId: "dev_1", saat: 18 }));
  fireEvent.click(await screen.findByRole("button", { name: "Onay yetkisini kaldır" }));
  await waitFor(() => expect(client.request).toHaveBeenCalledWith("uzak.onay_yetkisi", { cihazId: "dev_2", saat: 0 }));
  expect(screen.getByText(/Onay yetkisi: 1 sa kaldı|Onay yetkisi: 2 sa kaldı/)).toBeTruthy();
});

it("eşleştirme kodu istenirken seçilirse cihaza 18 saatlik onay yetkisi eklenir", async () => {
  const client = fakeClient();
  render(<RemoteAccess client={client} />);
  fireEvent.click(await screen.findByLabelText(/Eşleşen cihaz 18 saat onay verebilsin/));
  fireEvent.click(screen.getByRole("button", { name: "Telefon için eşleştirme kodu oluştur" }));
  await waitFor(() => expect(client.request).toHaveBeenCalledWith("uzak.eslestir_baslat", {
    kanal: "pwa", kapsamlar: ["project.read", "agent.run", "agent.cancel"], onaySaat: 18,
  }));
});

it("kalan onay yetkisi saat ya da dakika olarak yazılır; dolmuşsa yok", () => {
  expect(approvalTrustLabel(undefined, 1000)).toBe("Onay yetkisi yok");
  expect(approvalTrustLabel(1000 + 7200, 1000)).toBe("Onay yetkisi: 2 sa kaldı");
  expect(approvalTrustLabel(1000 + 600, 1000)).toBe("Onay yetkisi: 10 dk kaldı");
});

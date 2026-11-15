/** Arka plan görevleri ve açık oturumlar paneli (P-048, P-060). */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { BackgroundAgentsPanel, type BackgroundClient } from "./BackgroundAgentsPanel";

afterEach(cleanup);

function fakeClient(state: Record<string, unknown>) {
  const calls: Array<[string, Record<string, unknown>]> = [];
  const client: BackgroundClient = {
    request: vi.fn(async (name: string, data: Record<string, unknown>) => {
      calls.push([name, data]);
      if (name === "arkaplan.durum") return state;
      if (name === "arkaplan.goster") return { ok: true, sonuc: "Rapor: 3 madde", olaylar: "ToolExecuted read_file" };
      if (name === "arkaplan.baslat" && data.gorev === "hata") return { ok: false, metin: "Aynı anda en çok 4 arka plan görevi çalışabilir" };
      return { ok: true };
    }),
  };
  return { client, calls };
}

const status = {
  ok: true,
  acik: true,
  gorevler: [
    { id: "a1b2c3d4", name: "rapor", status: "girdi_bekliyor", durum_etiketi: "girdi bekliyor", etkin: true, question: "run_shell onayı: npm test", summary: "", prompt: "rapor yaz" },
    { id: "b1b2c3d4", name: "temizlik", status: "tamamlandi", durum_etiketi: "tamamlandı", etkin: false, summary: "2 dosya silindi", prompt: "temizle" },
  ],
  oturumlar: [{ id: "c1c2c3c4", ad: "terminal", tur: "repl", kok: "/proje" }],
  bekleyen: [{ no: 1, kimden: "terminal", metin: "testleri koştur" }],
  bildirimler: ["⏸ arka plan görevi 'rapor' girdi bekliyor"],
};

it("görevleri, onay düğmelerini, oturumları ve bekleyen mesajı gösterir; bildirimi iletir", async () => {
  const notify = vi.fn();
  const { client, calls } = fakeClient(status);
  render(<BackgroundAgentsPanel client={client} notify={notify} onCommand={vi.fn()} pollMs={60_000} />);

  expect(await screen.findByText("run_shell onayı: npm test")).toBeTruthy();
  expect(screen.getByText("2 dosya silindi")).toBeTruthy();
  expect(screen.getByText("testleri koştur")).toBeTruthy();
  expect(notify).toHaveBeenCalledWith("Fusion arka plan", "⏸ arka plan görevi 'rapor' girdi bekliyor");

  fireEvent.click(screen.getByRole("button", { name: "Onayla" }));
  await waitFor(() => expect(calls).toContainEqual(["arkaplan.cevapla", { id: "a1b2c3d4", cevap: "evet" }]));
  fireEvent.click(screen.getByRole("button", { name: "rapor görevini durdur" }));
  await waitFor(() => expect(calls).toContainEqual(["arkaplan.durdur", { id: "a1b2c3d4" }]));
  fireEvent.click(screen.getByRole("button", { name: "temizlik kaydını sil" }));
  await waitFor(() => expect(calls).toContainEqual(["arkaplan.sil", { id: "b1b2c3d4" }]));
});

it("yeni görev başlatır, devam mesajı ve oturuma mesaj gönderir, hata metnini gösterir", async () => {
  const { client, calls } = fakeClient(status);
  render(<BackgroundAgentsPanel client={client} notify={vi.fn()} pollMs={60_000} />);
  await screen.findByText("rapor");

  fireEvent.change(screen.getByLabelText("Arka planda çalışacak görev"), { target: { value: "testleri yaz" } });
  fireEvent.click(screen.getByRole("button", { name: "Arka planda başlat" }));
  await waitFor(() => expect(calls).toContainEqual(["arkaplan.baslat", { gorev: "testleri yaz" }]));

  fireEvent.change(screen.getByLabelText("temizlik görevine mesaj"), { target: { value: "logları da sil" } });
  fireEvent.submit(screen.getByLabelText("temizlik görevine mesaj").closest("form")!);
  await waitFor(() => expect(calls).toContainEqual(["arkaplan.mesaj", { id: "b1b2c3d4", metin: "logları da sil" }]));

  fireEvent.change(screen.getByLabelText("Hedef oturum"), { target: { value: "c1c2c3c4" } });
  fireEvent.change(screen.getByLabelText("Oturuma mesaj"), { target: { value: "bitti" } });
  fireEvent.submit(screen.getByLabelText("Oturuma mesaj").closest("form")!);
  await waitFor(() => expect(calls).toContainEqual(["esler.gonder", { hedef: "c1c2c3c4", metin: "bitti" }]));

  fireEvent.change(screen.getByLabelText("Arka planda çalışacak görev"), { target: { value: "hata" } });
  fireEvent.click(screen.getByRole("button", { name: "Arka planda başlat" }));
  expect((await screen.findByRole("alert")).textContent).toContain("en çok 4");
});

it("bekleyen mesajı tura almak etiketli komut yolunu kullanır; ayrıntı sonucu gösterir", async () => {
  const onCommand = vi.fn();
  const { client } = fakeClient(status);
  render(<BackgroundAgentsPanel client={client} notify={vi.fn()} onCommand={onCommand} pollMs={60_000} />);
  await screen.findByText("testleri koştur");

  fireEvent.click(screen.getByRole("button", { name: "Tura al" }));
  expect(onCommand).toHaveBeenCalledWith("/list-agents al 1");
  fireEvent.click(screen.getAllByRole("button", { name: "Ayrıntı" })[0]);
  expect(await screen.findByText(/Rapor: 3 madde/)).toBeTruthy();
});

it("ayar kapalıysa başlatma formu yerine açıklama gösterir", async () => {
  const { client } = fakeClient({ ...status, acik: false, gorevler: [], bekleyen: [], oturumlar: [], bildirimler: [] });
  render(<BackgroundAgentsPanel client={client} notify={vi.fn()} pollMs={60_000} />);
  expect(await screen.findByText(/runtime.background_agents/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Arka planda başlat" })).toBeNull();
});

it("serbest metinli soruyu cevaplar; seçenek düğmesi ve tam onay çağrısı gösterilir", async () => {
  const asking = {
    ...status,
    gorevler: [
      { id: "d1d2d3d4", name: "soran", status: "girdi_bekliyor", durum_etiketi: "girdi bekliyor", etkin: true, question: "Hangi veritabanı?", soru: { tur: "soru", ozet: "Hangi veritabanı?", secenekler: ["sqlite"], onerilen: "sqlite" } },
      { id: "e1e2e3e4", name: "onayci", status: "girdi_bekliyor", durum_etiketi: "girdi bekliyor", etkin: true, question: "run_shell onayı: rm…", soru: { tur: "onay", ozet: "run_shell onayı: rm…", arguman: '{"command": "rm -rf build"}', tehlike: "kalıcı silme" } },
    ],
  };
  const { client, calls } = fakeClient(asking);
  render(<BackgroundAgentsPanel client={client} notify={vi.fn()} pollMs={60_000} />);
  await screen.findByText("soran");

  // Soru türünde onay düğmesi yok; cevap kutusu `arkaplan.cevapla` çağırır (mesaj değil).
  expect(screen.getAllByRole("button", { name: "Onayla" })).toHaveLength(1);
  fireEvent.change(screen.getByLabelText("soran sorusuna cevap"), { target: { value: "Postgres" } });
  fireEvent.click(screen.getByRole("button", { name: "Cevapla" }));
  await waitFor(() => expect(calls).toContainEqual(["arkaplan.cevapla", { id: "d1d2d3d4", cevap: "Postgres" }]));
  expect(calls.some(([name]) => name === "arkaplan.mesaj")).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "sqlite" }));
  await waitFor(() => expect(calls).toContainEqual(["arkaplan.cevapla", { id: "d1d2d3d4", cevap: "sqlite" }]));

  expect(screen.getByLabelText("onayci onaylanacak çağrı").textContent).toContain("rm -rf build");
  expect(screen.getByText("Risk: kalıcı silme")).toBeTruthy();
});

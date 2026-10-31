import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { describeSessionCron, SessionCronPanel } from "./SessionCronPanel";

const gorev = { id: "ab12", prompt: "testleri koştur", kind: "aralik", next_due: 1_800_000_000, every_s: 600, cron: "", runs: 2, source: "kullanici" };

function makeClient(gorevler: unknown[]) {
  let current = gorevler;
  const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
    if (name === "cron.sil") {
      current = current.filter((item) => (item as { id: string }).id !== data.id);
      return { ok: true, silinen: 1 };
    }
    return { ok: true, gorevler: current };
  });
  return { request };
}

// P-038 eksik yüzeyi: masaüstünde oturum döngüleri görülür ve durdurulur.
it("sohbetin döngülerini listeler ve durdurur", async () => {
  const client = makeClient([gorev, { ...gorev, id: "cd34", prompt: "uyan", kind: "tek", source: "ajan" }]);
  render(<SessionCronPanel client={client} />);

  expect(await screen.findByText("testleri koştur")).toBeTruthy();
  expect(screen.getByText(/Her 10 dk/)).toBeTruthy();
  expect(screen.getByText(/ajan kurdu/)).toBeTruthy();

  fireEvent.click(screen.getByRole("button", { name: "testleri koştur döngüsünü durdur" }));
  await waitFor(() => expect(client.request).toHaveBeenCalledWith("cron.sil", { id: "ab12" }));
  await waitFor(() => expect(screen.queryByText("testleri koştur")).toBeNull());
});

it("boşta yol gösterir, bozuk satırı atlar, istemci yoksa hiç çizilmez", async () => {
  const { container, rerender } = render(<SessionCronPanel client={null} />);
  expect(container.textContent).toBe("");

  rerender(<SessionCronPanel client={makeClient([{ id: 1 }])} />);
  expect(await screen.findByText(/Döngü yok/)).toBeTruthy();
});

it("durdurma reddedilirse hata metni gösterir", async () => {
  const request = vi.fn(async (name: string) => (name === "cron.sil" ? { ok: false, metin: "Görev bulunamadı: ab12" } : { ok: true, gorevler: [gorev] }));
  render(<SessionCronPanel client={{ request }} />);
  fireEvent.click(await screen.findByRole("button", { name: "testleri koştur döngüsünü durdur" }));
  expect((await screen.findByRole("alert")).textContent).toContain("Görev bulunamadı");
});

it("zamanlamayı kısa Türkçe ifadeye çevirir", () => {
  expect(describeSessionCron({ ...gorev, every_s: 7200 })).toBe("Her 2 saat");
  expect(describeSessionCron({ ...gorev, kind: "cron", cron: "0 9 * * *" })).toBe("Cron 0 9 * * *");
  expect(describeSessionCron({ ...gorev, kind: "tek" })).toBe("Bir kez");
});

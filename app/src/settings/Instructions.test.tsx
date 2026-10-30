import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { Instructions } from "./Instructions";

afterEach(cleanup);

function istemci(yanit: (ad: string) => Promise<unknown>) {
  return { request: vi.fn(async (ad: string) => yanit(ad)) } as unknown as ProtocolClient;
}

// Ölçüldü (29 Ekim, U2-36): save reddedilince busy sonsuza dek true kalıyor, hata görünmüyordu;
// okuma başarısızsa kullanıcı bilmeden mevcut talimatın üzerine yazabiliyordu.
it("kayıt reddedilirse hata gösterir ve Kaydet yeniden açılır", async () => {
  let kayitDenemesi = 0;
  const client = istemci(async (ad) => {
    if (ad === "ayar.talimat") return { ok: true, metin: "eski", sinir: 4000 };
    kayitDenemesi += 1;
    if (kayitDenemesi === 1) throw new Error("köprü koptu");
    return { ok: true };
  });
  render(<Instructions client={client} />);
  const kutu = await screen.findByLabelText("Kalıcı talimat");
  await waitFor(() => expect((kutu as HTMLTextAreaElement).value).toBe("eski"));
  fireEvent.change(kutu, { target: { value: "yeni" } });
  fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));

  expect((await screen.findByRole("status")).textContent).toContain("kaydedilemedi");
  const kaydet = screen.getByRole("button", { name: "Kaydet" }) as HTMLButtonElement;
  expect(kaydet.disabled).toBe(false);
  fireEvent.click(kaydet);
  expect((await screen.findByRole("status")).textContent).toContain("kaydedildi");
});

it("okuma başarısızsa düzenleme ve kayıt kapalıdır, yeniden okuyunca açılır", async () => {
  let okuma = 0;
  const client = istemci(async (ad) => {
    if (ad !== "ayar.talimat") return { ok: true };
    okuma += 1;
    return okuma === 1 ? { ok: false, metin: "Veri klasörü okunamadı." } : { ok: true, metin: "mevcut", sinir: 4000 };
  });
  render(<Instructions client={client} />);
  expect((await screen.findByRole("status")).textContent).toContain("Veri klasörü okunamadı.");
  expect((screen.getByLabelText("Kalıcı talimat") as HTMLTextAreaElement).disabled).toBe(true);
  expect((screen.getByRole("button", { name: "Kaydet" }) as HTMLButtonElement).disabled).toBe(true);

  fireEvent.click(screen.getByRole("button", { name: "Yeniden oku" }));
  await waitFor(() => expect((screen.getByLabelText("Kalıcı talimat") as HTMLTextAreaElement).value).toBe("mevcut"));
  expect((screen.getByLabelText("Kalıcı talimat") as HTMLTextAreaElement).disabled).toBe(false);
});

// P-015: tur başında yüklenen katmanlar (kullanıcı + proje) ve kırpma notu görünür.
it("yüklenen talimat katmanlarını ve kırpma notunu listeler", async () => {
  const client = istemci(async (ad) => {
    if (ad === "ayar.talimat") return {
      ok: true, metin: "", sinir: 4000,
      katmanlar: [
        { kaynak: "~/.claude/CLAUDE.md", katman: "kullanici", karakter: 120, kirpilan: 0, guvenilir: true },
        { kaynak: "CLAUDE.md", katman: "proje", karakter: 8000, kirpilan: 512, guvenilir: false },
        null,
      ],
      notlar: ["@../gizli.md: kök dışı ya da izinsiz import atlandı"],
    };
    return { ok: true };
  });
  render(<Instructions client={client} />);
  const liste = await screen.findByLabelText("Yüklenen talimat katmanları");
  expect(liste.textContent).toContain("~/.claude/CLAUDE.md");
  expect(liste.textContent).toContain("Kullanıcı · 120 karakter");
  expect(liste.textContent).toContain("512 kırpıldı");
  expect(liste.textContent).toContain("depo içeriği");
  expect(screen.getByRole("note").textContent).toContain("import atlandı");
});

it("katman yoksa /init ipucu gösterir", async () => {
  const client = istemci(async () => ({ ok: true, metin: "", sinir: 4000, katmanlar: [] }));
  render(<Instructions client={client} />);
  await screen.findByLabelText("Kalıcı talimat");
  expect(screen.getByText(/\/init/).textContent).toContain("/init");
});

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
  const liste = await screen.findByLabelText("Talimat dosyaları ve kurallar");
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

// P-021: önerilen düzeltmeler listelenir; "Talimat oluştur" /init komutunu çalıştırır.
it("önerileri listeler ve Talimat oluştur /init gönderir", async () => {
  const client = istemci(async () => ({
    ok: true, metin: "", sinir: 4000, katmanlar: [],
    oneriler: ["Proje talimat dosyası yok: `/init` ile AGENTS.md oluştur."],
  }));
  const calistir = vi.fn();
  render(<Instructions client={client} onRunCommand={calistir} />);
  expect((await screen.findByLabelText("Talimat önerileri")).textContent).toContain("AGENTS.md");
  fireEvent.click(screen.getByRole("button", { name: "Talimat oluştur (/init)" }));
  expect(calistir).toHaveBeenCalledWith("/init");
});

// Eksik yüzey (31 Ekim): `.claude/rules` kuralları katman listesinde yoktu; "Kural" etiketi
// hiç kullanılmıyordu. Kural satırı kapsamını (paths) ya da "her yerde" gösterir.
it("kural dosyalarını kapsamıyla listeler", async () => {
  const client = istemci(async (ad) => {
    if (ad === "ayar.talimat") return {
      ok: true, metin: "", sinir: 4000,
      katmanlar: [
        { kaynak: ".claude/rules/react.md", katman: "kural", karakter: 90, kirpilan: 0, guvenilir: false, kapsam: ["src/**/*.tsx", "*.css"] },
        { kaynak: "~/.claude/rules/genel.md", katman: "kural", karakter: 40, kirpilan: 0, guvenilir: true, kapsam: [] },
      ],
    };
    return { ok: true };
  });
  render(<Instructions client={client} />);
  const liste = await screen.findByLabelText("Talimat dosyaları ve kurallar");
  expect(liste.textContent).toContain("Kural · 90 karakter · src/**/*.tsx, *.css · depo içeriği");
  expect(liste.textContent).toContain("Kural · 40 karakter · her yerde");
});

it("talimat dosyaları varsayılan kapalı açılır-kapanır listede, başlıkta sayıyla durur", async () => {
  const katmanlar = Array.from({ length: 12 }, (_, sira) => ({ kaynak: `/Users/ornek/cok/uzun/bir/yol/kural-${sira}.md`, katman: "kural", karakter: 100, kirpilan: 0, guvenilir: true, kapsam: [] }));
  const client = istemci(async (ad) => ad === "ayar.talimat" ? { ok: true, metin: "", sinir: 4000, katmanlar } : { ok: true });
  render(<Instructions client={client} />);
  const ozet = await screen.findByText("Talimat dosyaları ve kurallar (12)");
  const acilir = ozet.closest("details") as HTMLDetailsElement;
  expect(acilir.open).toBe(false);
  expect(screen.getByLabelText("Talimat dosyaları ve kurallar").querySelectorAll("li")).toHaveLength(12);
  fireEvent.click(ozet);
  expect(acilir.open).toBe(true);
});

// Claude Code (#145): dış `@import` ilk görüldüğünde dosyaları listeleyen onay istenir.
it("kararı verilmemiş dış importları listeler ve onayı gönderir", async () => {
  let karar: unknown = null;
  const client = {
    request: vi.fn(async (ad: string, veri: unknown) => {
      if (ad === "ayar.dis_import_karari") {
        karar = veri;
        return { ok: true, metin: "Dış importlara izin verildi." };
      }
      return { ok: true, metin: "", sinir: 4000, dis_importlar: karar ? [] : ["/ortak/kurallar.md"] };
    }),
  } as unknown as ProtocolClient;
  render(<Instructions client={client} />);

  expect(await screen.findByText("/ortak/kurallar.md")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "İzin ver" }));

  await waitFor(() => expect(karar).toEqual({ onay: true }));
  await waitFor(() => expect(screen.queryByText("/ortak/kurallar.md")).toBeNull());
});

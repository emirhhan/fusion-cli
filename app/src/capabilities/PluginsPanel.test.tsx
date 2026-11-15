import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { PluginsPanel, componentSummary } from "./PluginsPanel";

afterEach(cleanup);

const bilesen = { beceri: 2, komut: 1, ajan: 0, stil: 0, kanca: true, mcp: false };
const onizleme = { ad: "bicimci", surum: "0.1.0", aciklama: "Biçimler", yazar: "Ekip", bilesenler: bilesen, kanca_sayisi: 1, kancalar: ["PostToolUse [Edit]: ${CLAUDE_PLUGIN_ROOT}/bicimle.sh"], kancalar_calismaz: true, mcp: [], calistirilabilir: true, baglam_maliyeti: 42, uyarilar: ["plugin.json yok"], hatalar: [], karma: "a".repeat(64) };

function client() {
  let kurulu: Record<string, unknown>[] = [];
  const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
    if (name === "eklenti.listele") return { ok: true, hepsi_kapali: false, eklentiler: kurulu, pazarlar: [] };
    if (name === "eklenti.onizle") return { ok: true, onizleme };
    if (name === "eklenti.kur") {
      kurulu = [{ ad: "bicimci", surum: "0.1.0", aciklama: "Biçimler", durum: "etkin", ayrinti: "", kaynak: String(data.kaynak), pazar: "", etkin: true, calistirilabilir: true, bilesenler: bilesen }];
      return { ok: true, yenile: true, eklenti: kurulu[0] };
    }
    if (name === "eklenti.etkinlik") {
      kurulu = kurulu.map((item) => ({ ...item, etkin: data.etkin, durum: data.etkin ? "etkin" : "kapalı" }));
      return { ok: true, yenile: true, hepsi_kapali: false, eklentiler: kurulu, pazarlar: [] };
    }
    if (name === "eklenti.kaldir") { kurulu = []; return { ok: true, yenile: true, eklentiler: [], pazarlar: [] }; }
    return { ok: false, metin: "bilinmeyen" };
  });
  return { request } as unknown as ProtocolClient & { request: typeof request };
}

it("önizleme gösterir, çalıştırılabilir eklentiyi onayla kurar, kapatır ve iki adımda kaldırır", async () => {
  const api = client();
  const changed = vi.fn();
  render(<PluginsPanel client={api} onChanged={changed} />);
  expect(await screen.findByText(/Kurulu eklenti yok/)).toBeTruthy();

  fireEvent.change(screen.getByRole("textbox", { name: "Eklenti kaynağı" }), { target: { value: "./bicimci" } });
  fireEvent.click(screen.getByRole("button", { name: "Önizle" }));
  expect(await screen.findByRole("note")).toBeTruthy();
  expect(screen.getByText(/bağlam ~42 token/)).toBeTruthy();
  expect(screen.getByText("PostToolUse [Edit]: ${CLAUDE_PLUGIN_ROOT}/bicimle.sh")).toBeTruthy();
  expect(screen.getByText(/kancalar onaylansa da tetiklenmez/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Onaylıyorum, kur" }));
  await waitFor(() => expect(api.request).toHaveBeenCalledWith("eklenti.kur", { kaynak: "./bicimci", onay: true, beklenen_karma: "a".repeat(64) }));
  expect(await screen.findByText("bicimci 0.1.0")).toBeTruthy();
  expect(changed).toHaveBeenCalled();

  fireEvent.click(screen.getByRole("switch", { name: "bicimci etkin" }));
  await waitFor(() => expect(api.request).toHaveBeenCalledWith("eklenti.etkinlik", { ad: "bicimci", etkin: false }));

  fireEvent.click(screen.getByRole("button", { name: "Kaldır" }));
  fireEvent.click(screen.getByRole("button", { name: "Evet, kaldır" }));
  await waitFor(() => expect(api.request).toHaveBeenCalledWith("eklenti.kaldir", { ad: "bicimci" }));
  expect(await screen.findByText(/Kurulu eklenti yok/)).toBeTruthy();
});

it("hatalı önizlemede kur düğmesi kapalı ve bileşen özeti türkçe", async () => {
  const request = vi.fn(async (name: string) => {
    if (name === "eklenti.listele") return { ok: true, eklentiler: [], pazarlar: [] };
    return { ok: true, onizleme: { ...onizleme, calistirilabilir: false, hatalar: ["bileşen yok"] } };
  });
  render(<PluginsPanel client={{ request } as unknown as ProtocolClient} />);
  fireEvent.change(await screen.findByRole("textbox", { name: "Eklenti kaynağı" }), { target: { value: "x" } });
  fireEvent.click(screen.getByRole("button", { name: "Önizle" }));
  expect(((await screen.findByRole("button", { name: "Kur" })) as HTMLButtonElement).disabled).toBe(true);
  expect(componentSummary(bilesen)).toBe("2 beceri · 1 komut · kanca");
});

it("güncelle önce yeni içeriği gösterir, doğrula sonucu bildirir, pazar güncellenir", async () => {
  const kurulu = { ad: "bicimci", surum: "0.1.0", aciklama: "", durum: "etkin", ayrinti: "", kaynak: "./b", pazar: "", etkin: true, calistirilabilir: true, bilesenler: bilesen };
  const yeni = { ...onizleme, surum: "0.2.0", kancalar: ["Stop: yeni"], karma: "c".repeat(64) };
  const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
    if (name === "eklenti.listele") return { ok: true, eklentiler: [kurulu], pazarlar: [{ ad: "ekip", kaynak: "o/r", tur: "git" }] };
    if (name === "eklenti.guncelle" && data.onay !== true) return { ok: false, onay_gerekli: true, metin: "incele", onizleme: yeni };
    if (name === "eklenti.guncelle") return { ok: true, yenile: true, guncel: false, eklentiler: [{ ...kurulu, surum: "0.2.0" }], pazarlar: [{ ad: "ekip", kaynak: "o/r", tur: "git" }] };
    if (name === "eklenti.dogrula") return { ok: true, gecerli: true, butunluk: "etkin", hatalar: [], uyarilar: ["açıklama yok"] };
    if (name === "eklenti.pazar_guncelle") return { ok: true, eklentiler: [kurulu], pazarlar: [{ ad: "ekip", kaynak: "o/r", tur: "git" }] };
    return { ok: false };
  });
  render(<PluginsPanel client={{ request } as unknown as ProtocolClient} />);
  fireEvent.click(await screen.findByRole("button", { name: "bicimci güncelle" }));
  expect(await screen.findByText("Stop: yeni")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Onaylıyorum, güncelle" }));
  await waitFor(() => expect(request).toHaveBeenCalledWith("eklenti.guncelle", { ad: "bicimci", onay: true, beklenen_karma: "c".repeat(64) }));
  expect(await screen.findByText("bicimci güncellendi.")).toBeTruthy();

  fireEvent.click(screen.getByRole("button", { name: "bicimci doğrula" }));
  expect(await screen.findByText(/bicimci geçerli · bütünlük: etkin · açıklama yok/)).toBeTruthy();

  fireEvent.click(screen.getByRole("tab", { name: /Pazarlar/ }));
  fireEvent.click(screen.getByRole("button", { name: "ekip pazarını güncelle" }));
  await waitFor(() => expect(request).toHaveBeenCalledWith("eklenti.pazar_guncelle", { ad: "ekip" }));
});

it("pazar kaldırma onay ister, eklentilerin ve verilerinin de silineceğini söyler, kaldırılanları bildirir", async () => {
  const pazar = { ad: "ekip", kaynak: "o/r", tur: "git" };
  const request = vi.fn(async (name: string) => {
    if (name === "eklenti.listele") return { ok: true, eklentiler: [], pazarlar: [pazar] };
    if (name === "eklenti.pazar_kaldir") return { ok: true, eklentiler: [], pazarlar: [], kaldirilan: ["rapor", "ozet"] };
    return { ok: false };
  });
  render(<PluginsPanel client={{ request } as unknown as ProtocolClient} />);
  fireEvent.click(await screen.findByRole("tab", { name: /Pazarlar/ }));
  fireEvent.click(await screen.findByRole("button", { name: "ekip pazarını kaldır" }));
  expect(request).not.toHaveBeenCalledWith("eklenti.pazar_kaldir", expect.anything());
  expect(screen.getByText(/bu pazardan kurulan bütün eklentiler, ayarları ve verileri de silinir/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Evet, pazarı kaldır" }));
  await waitFor(() => expect(request).toHaveBeenCalledWith("eklenti.pazar_kaldir", { ad: "ekip" }));
  expect(await screen.findByText("ekip pazarı kaldırıldı. Ayrıca bu pazardan 2 eklenti kaldırıldı: rapor, ozet")).toBeTruthy();
});

it("kapsam seçer, oturumluk ve işaretli eklentileri, bildirimleri gösterir, auto-update anahtarı ve komut onayı çalışır", async () => {
  let otomatik = false;
  const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
    const list = {
      ok: true, hepsi_kapali: false, eklentiler: [],
      pazarlar: [{ ad: "ekip", kaynak: "./pazar", tur: "yerel", otomatik_guncelle: otomatik }],
      oturumluk: [{ kimlik: "deneme@inline", ad: "deneme", kapsam: "session", surum: "", aciklama: "", etkin: true }],
      isaretli: [{ kimlik: "eski@ekip", ad: "eski", pazar: "ekip", tarih: "2026-11-01" }],
      bildirimler: name === "eklenti.listele" ? ["Plugin updated: x · Run /reload-plugins to apply"] : [],
    };
    if (name === "eklenti.listele") return list;
    if (name === "eklenti.onizle") return { ok: true, onizleme: { ...onizleme, calistirilabilir: false } };
    if (name === "eklenti.kur" && !data.komut_onayi) return { ok: false, komut_onayi_gerekli: true, metin: "onay", komut: { kind: "command_source", pluginId: "uret@ekip", command: "echo /x", mode: "copy", sha256: "f".repeat(64) } };
    if (name === "eklenti.kur") return { ok: true, yenile: true };
    if (name === "eklenti.pazar_otomatik") { otomatik = data.acik === true; return { ...list, pazarlar: [{ ...list.pazarlar[0], otomatik_guncelle: otomatik }] }; }
    return { ok: false, metin: "bilinmeyen" };
  });
  render(<PluginsPanel client={{ request } as unknown as ProtocolClient} />);
  expect(await screen.findByText("deneme@inline")).toBeTruthy();
  expect(screen.getByText("eski@ekip")).toBeTruthy();
  expect(screen.getByText(/Plugin updated: x/)).toBeTruthy();

  fireEvent.change(screen.getByRole("combobox", { name: "Kurulum kapsamı" }), { target: { value: "project" } });
  fireEvent.change(screen.getByRole("textbox", { name: "Eklenti kaynağı" }), { target: { value: "uret@ekip" } });
  fireEvent.click(screen.getByRole("button", { name: "Önizle" }));
  fireEvent.click(await screen.findByRole("button", { name: "Kur" }));
  await waitFor(() => expect(request).toHaveBeenCalledWith("eklenti.kur", { kaynak: "uret@ekip", onay: false, beklenen_karma: "a".repeat(64), kapsam: "project" }));
  expect(await screen.findByText("echo /x")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Komutu onayla ve sürdür" }));
  await waitFor(() => expect(request).toHaveBeenCalledWith("eklenti.kur", { kaynak: "uret@ekip", onay: false, beklenen_karma: "a".repeat(64), kapsam: "project", komut_onayi: "f".repeat(64) }));

  fireEvent.click(screen.getByRole("tab", { name: /Pazarlar/ }));
  fireEvent.click(screen.getByRole("switch", { name: "ekip otomatik güncelleme" }));
  await waitFor(() => expect(request).toHaveBeenCalledWith("eklenti.pazar_otomatik", { ad: "ekip", acik: true }));
});

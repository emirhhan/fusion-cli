import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Akis } from "./akis";
import { AkisTuvali } from "./AkisTuvali";

afterEach(cleanup);

const SECENEKLER = [
  { deger: "nim/flux", etiket: "FLUX", referans: false },
  { deger: "gemini_web/main", etiket: "Gemini", referans: true },
];

function akis(): Akis {
  return {
    ad: "deneme",
    dugumler: [
      { id: "m", tur: "metin", x: 0, y: 0, istem: "kask" },
      { id: "u", tur: "uret", x: 300, y: 0, saglayici: "nim/flux" },
    ],
    baglantilar: [],
  };
}

function ciz(baslangic: Akis, onChange = vi.fn()) {
  render(
    <AkisTuvali
      akis={baslangic}
      calisiyor={false}
      onChange={onChange}
      onGorselSec={vi.fn()}
      onIndir={vi.fn()}
      secenekler={SECENEKLER}
      toUrl={(yol) => `asset://${yol}`}
    />,
  );
  return onChange;
}

describe("AkisTuvali — Flora benzeri etkileşim", () => {
  it("çıkış portundan sürükleyip hedef düğümde bırakınca bağlantı kurar", () => {
    const onChange = ciz(akis());
    const hedef = document.querySelector('[data-dugum-id="u"]') as HTMLElement;
    document.elementFromPoint = vi.fn(() => hedef);

    fireEvent.pointerDown(screen.getByRole("button", { name: "Metin çıkışından bağlantı başlat" }), { clientX: 220, clientY: 22 });
    fireEvent.pointerMove(screen.getByRole("region", { name: "Görsel iş akışı tuvali" }), { clientX: 310, clientY: 22 });
    fireEvent.pointerUp(screen.getByRole("region", { name: "Görsel iş akışı tuvali" }), { clientX: 310, clientY: 22 });

    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ baglantilar: [{ kaynak: "m", hedef: "u" }] }));
  });

  it("tıklayarak bağlama yolu (klavye) çalışmaya devam eder", () => {
    const onChange = ciz(akis());
    fireEvent.click(screen.getByRole("button", { name: "Metin çıkışından bağlantı başlat" }));
    fireEvent.click(screen.getByRole("button", { name: "Üret girdisine bağla" }));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ baglantilar: [{ kaynak: "m", hedef: "u" }] }));
  });

  it("yakınlaştırma düğmeleri ölçeği değiştirir ve sıfırlanır", () => {
    ciz(akis());
    const sahne = document.querySelector(".akis-tuvali__sahne") as HTMLElement;
    fireEvent.click(screen.getByRole("button", { name: "Yakınlaştır" }));
    expect(sahne.style.transform).toContain("scale(1.1)");
    fireEvent.click(screen.getByRole("button", { name: "Görünümü sıfırla" }));
    expect(sahne.style.transform).toContain("scale(1)");
  });

  it("boş alanı sürükleyince tuval kayar", () => {
    ciz(akis());
    const tuval = screen.getByRole("region", { name: "Görsel iş akışı tuvali" });
    fireEvent.pointerDown(tuval, { clientX: 500, clientY: 400 });
    fireEvent.pointerMove(tuval, { clientX: 540, clientY: 430 });
    fireEvent.pointerUp(tuval, { clientX: 540, clientY: 430 });
    expect((document.querySelector(".akis-tuvali__sahne") as HTMLElement).style.transform).toContain("translate(40px, 30px)");
  });

  it("birden çok varyasyonda seçilen küçük resim düğümün çıktısı olur", () => {
    const baslangic = akis();
    const onChange = ciz({
      ...baslangic,
      dugumler: [baslangic.dugumler[0], { ...baslangic.dugumler[1], sonuclar: ["/g/a.jpg", "/g/b.jpg"], yol: "/g/a.jpg", durum: "bitti" }],
    });
    fireEvent.click(screen.getByRole("radio", { name: "Varyasyon 2" }));
    const son = onChange.mock.calls.at(-1)?.[0] as Akis;
    expect(son.dugumler[1].yol).toBe("/g/b.jpg");
  });

  it("işlem düğümünde varyasyon sayısı seçilir", () => {
    const onChange = ciz(akis());
    fireEvent.change(screen.getByLabelText("Üret varyasyon sayısı"), { target: { value: "3" } });
    expect((onChange.mock.calls.at(-1)?.[0] as Akis).dugumler[1].adet).toBe(3);
  });
});

describe("AkisTuvali — dalga 4 (U3-06, U3-13, U3-14)", () => {
  it("Ctrl+tekerlek pasif olmayan dinleyiciyle yakınlaştırır ve sayfa varsayılanını engeller", () => {
    ciz(akis());
    const tuval = screen.getByRole("region", { name: "Görsel iş akışı tuvali" });
    const olay = new WheelEvent("wheel", { ctrlKey: true, deltaY: -100, cancelable: true, bubbles: true });
    act(() => { tuval.dispatchEvent(olay); });
    expect(olay.defaultPrevented).toBe(true);
    expect(screen.getByRole("button", { name: "Görünümü sıfırla" }).textContent).toBe("110%");
    const duz = new WheelEvent("wheel", { deltaY: -100, cancelable: true, bubbles: true });
    act(() => { tuval.dispatchEvent(duz); });
    expect(duz.defaultPrevented).toBe(false);
  });

  it("işaretçi iptal olunca yarım kalan düğüm sürüklemesi sonraki harekette sürmez", () => {
    const onChange = ciz(akis());
    const tuval = screen.getByRole("region", { name: "Görsel iş akışı tuvali" });
    const baslik = document.querySelector('[data-dugum-id="m"] header') as HTMLElement;
    fireEvent.pointerDown(baslik, { clientX: 10, clientY: 10 });
    fireEvent.pointerMove(tuval, { clientX: 40, clientY: 40 });
    expect(onChange).toHaveBeenCalledTimes(1);
    fireEvent.pointerCancel(tuval);
    fireEvent.pointerMove(tuval, { clientX: 90, clientY: 90 });
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it("seçili sağlayıcı artık seçenekte yoksa select boş görünmez, kullanılamıyor diye işaretlenir", () => {
    ciz({ ...akis(), dugumler: [...akis().dugumler.slice(0, 1), { id: "u", tur: "uret", x: 300, y: 0, saglayici: "eski/sağlayıcı" }] });
    const secim = screen.getByLabelText("Üret sağlayıcısı") as HTMLSelectElement;
    expect(secim.value).toBe("eski/sağlayıcı");
    expect(screen.getByRole("option", { name: "eski/sağlayıcı (kullanılamıyor)" })).toBeTruthy();
  });
});

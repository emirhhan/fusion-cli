import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Approval } from "./Approval";
import { CloseConfirm } from "./CloseConfirm";
import { CommandSelector } from "./CommandSelector";
import { NewTaskDialog } from "./NewTaskDialog";
import { ShareDialog } from "./ShareDialog";

afterEach(cleanup);

/** Erişilebilir ad: aria-label, aria-labelledby, <label for>, sarmalayan label ya da metin. */
function adVar(node: HTMLElement): boolean {
  if (node.getAttribute("aria-label")?.trim()) return true;
  const by = node.getAttribute("aria-labelledby");
  if (by && by.split(/\s+/).some((id) => document.getElementById(id)?.textContent?.trim())) return true;
  if (node.id && document.querySelector(`label[for="${node.id}"]`)) return true;
  if (node.closest("label")?.textContent?.trim()) return true;
  if (node.tagName === "BUTTON") return Boolean(node.textContent?.trim());
  return false;
}

const secici = {
  adim: "a", tur: "secim" as const, baslik: "Seç", devam: { komut: "x", arguman_on_eki: "" },
  secenekler: [{ deger: "1", etiket: "Bir", aciklama: "ilk" }], serbest_metin: null,
};
const kartlar: [string, () => JSX.Element][] = [
  ["Approval", () => <Approval onCevap={vi.fn()} soru={{ tur: "onay", arac: "run_shell", baslik: "İzin?", secenekler: [{ deger: "once", etiket: "Evet" }, { deger: "deny", etiket: "Hayır" }] }} />],
  ["Approval soru", () => <Approval onCevap={vi.fn()} soru={{ tur: "soru", soru: "Ad?" }} />],
  ["CloseConfirm", () => <CloseConfirm onCancel={vi.fn()} onConfirm={vi.fn()} />],
  ["NewTaskDialog", () => <NewTaskDialog onCancel={vi.fn()} onChat={vi.fn()} onFolder={vi.fn()} open />],
  ["ShareDialog", () => <ShareDialog messages={[]} onClose={vi.fn()} title="t" />],
  ["CommandSelector", () => <CommandSelector busy={false} onCancel={vi.fn()} onSelect={vi.fn()} open selector={secici} />],
];

describe("diyalog erişilebilirliği (WP16 madde 4)", () => {
  it.each(kartlar)("%s: diyaloğun adı var, düğme ve girişlerin erişilebilir adı var", (_ad, cizim) => {
    render(cizim());
    const diyaloglar = [...document.querySelectorAll<HTMLElement>('[role="dialog"], [role="alertdialog"]')];
    expect(diyaloglar.length).toBeGreaterThan(0);
    for (const diyalog of diyaloglar) expect(adVar(diyalog), `diyalog adı: ${diyalog.outerHTML.slice(0, 80)}`).toBe(true);
    const adsiz = [...document.querySelectorAll<HTMLElement>("button, input, select, textarea")]
      .filter((node) => !adVar(node)).map((node) => node.outerHTML.slice(0, 100));
    expect(adsiz).toEqual([]);
  });

  it.each(kartlar.filter(([ad]) => !ad.startsWith("Approval")))("%s: modal diyalog aria-modal taşır ve Tab odağı dışarı kaçırmaz", (_ad, cizim) => {
    render(cizim());
    const diyalog = document.querySelector<HTMLElement>('[role="dialog"], [role="alertdialog"]')!;
    expect(diyalog.getAttribute("aria-modal")).toBe("true");
    const odaklanabilir = [...diyalog.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), [href]")];
    odaklanabilir[odaklanabilir.length - 1]?.focus();
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Tab" });
    // jsdom Tab'ı kendisi ilerletmez: tuzak ilk öğeye sarmalıyorsa odak diyalog içinde kalır.
    expect(diyalog.contains(document.activeElement)).toBe(true);
  });
});

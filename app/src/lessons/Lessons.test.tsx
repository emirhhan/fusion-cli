import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { Lessons, LESSON_PROGRESS_KEY, readProgress } from "./Lessons";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

const DERSLER = [
  { id: "ilk-proje", baslik: "İlk proje", ozet: "İlk adımı at.", adim_sayisi: 2 },
  { id: "basit-oyun-veya-site", baslik: "Basit oyun veya web sitesi", ozet: "Küçük bir sayfa üret.", adim_sayisi: 2 },
];

const ADIMLAR = [
  { id: "proje-sec", baslik: "Çalışma klasörünü tanı", aciklama: "Proje sekmesini aç.", onizleme: "Dosya ağacını göreceksin.", eylem: { tur: "sekme", hedef: "proje" } },
  { id: "ilk-gorev", baslik: "İlk görevini ver", aciklama: "Composer'a metin konur.", onizleme: "Bu projede neler var?", eylem: { tur: "composer", gorev: "Bu projede neler var?" } },
];

function client() {
  return {
    request: vi.fn(async (name: string) => {
      if (name === "ders.listele") return { ok: true, dersler: DERSLER };
      if (name === "ders.getir") return { ok: true, id: "ilk-proje", baslik: "İlk proje", ozet: "İlk adımı at.", adimlar: ADIMLAR };
      return { ok: true };
    }),
  } as unknown as ProtocolClient;
}

describe("Lessons", () => {
  it("sekiz dersin listesini ve adım sayılarını gösterir", async () => {
    render(<Lessons client={client()} onClose={() => undefined} onOpenTab={() => undefined} onUseComposer={() => undefined} />);

    expect(await screen.findByText("İlk proje")).toBeTruthy();
    expect(screen.getByText("Basit oyun veya web sitesi")).toBeTruthy();
    expect(screen.getAllByText("2 adım").length).toBe(2);
  });

  it("ders açar, adım ilerletir ve kaldığı yeri hatırlar", async () => {
    const { unmount } = render(
      <Lessons client={client()} onClose={() => undefined} onOpenTab={() => undefined} onUseComposer={() => undefined} />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /İlk proje/ }));
    expect(await screen.findByText("Çalışma klasörünü tanı")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Adımı tamamla" }));
    await waitFor(() => expect(readProgress()["ilk-proje"]).toBe(1));

    unmount();
    render(<Lessons client={client()} onClose={() => undefined} onOpenTab={() => undefined} onUseComposer={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: /İlk proje/ }));

    expect(await screen.findByText("2. adım / 2")).toBeTruthy();
  });

  it("composer eylemini gönderme yapmadan yalnız taslağa taşır, sekme eylemini sekmeye yönlendirir", async () => {
    const composer = vi.fn();
    const tab = vi.fn();
    render(<Lessons client={client()} onClose={() => undefined} onOpenTab={tab} onUseComposer={composer} />);

    fireEvent.click(await screen.findByRole("button", { name: /İlk proje/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Bunu dene" }));
    expect(tab).toHaveBeenCalledWith("proje");
    expect(composer).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Adımı tamamla" }));
    fireEvent.click(await screen.findByRole("button", { name: "Bunu dene" }));
    expect(composer).toHaveBeenCalledWith("Bu projede neler var?");
  });

  it("kayıtta yalnız ders kimliği ve adım tutulur; metin ve içerik saklanmaz", async () => {
    render(<Lessons client={client()} onClose={() => undefined} onOpenTab={() => undefined} onUseComposer={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: /İlk proje/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Adımı tamamla" }));

    const raw = window.localStorage.getItem(LESSON_PROGRESS_KEY) ?? "";
    expect(JSON.parse(raw)).toEqual({ surum: 1, ilerleme: { "ilk-proje": 1 } });
    expect(raw).not.toContain("Bu projede neler var");
    expect(raw).not.toContain("Çalışma klasörünü");
  });

  it("bozuk kayıt uygulamayı düşürmez, boş ilerlemeye döner", async () => {
    window.localStorage.setItem(LESSON_PROGRESS_KEY, "{bozuk");

    expect(readProgress()).toEqual({});
    render(<Lessons client={client()} onClose={() => undefined} onOpenTab={() => undefined} onUseComposer={() => undefined} />);
    expect(await screen.findByText("İlk proje")).toBeTruthy();
  });
});

describe("Lessons — klavye", () => {
  it("ders kartları ve adım eylemleri Tab ile sırayla odaklanabilir", async () => {
    render(<Lessons client={client()} onClose={() => undefined} onOpenTab={() => undefined} onUseComposer={() => undefined} />);

    const first = await screen.findByRole("button", { name: /İlk proje/ });
    first.focus();
    expect(document.activeElement).toBe(first);

    fireEvent.click(first);
    const tryButton = await screen.findByRole("button", { name: "Bunu dene" });
    tryButton.focus();
    expect(document.activeElement).toBe(tryButton);

    const back = screen.getByRole("button", { name: "← Dersler" });
    back.focus();
    expect(document.activeElement).toBe(back);
    fireEvent.click(back);
    expect(await screen.findByRole("button", { name: /Basit oyun/ })).toBeTruthy();
  });
});

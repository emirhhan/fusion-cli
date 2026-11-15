import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KitSendDialog, type KitRequest } from "./KitSendDialog";

afterEach(cleanup);

const KITLER = [
  { id: "kod", name: "Kod", fusionAllowed: true },
  { id: "kapali", name: "Kapalı", fusionAllowed: false },
];
const KAYIT = { taskId: "t1", title: "Fusion'dan görev", kind: "task", status: "completed", createdAt: 1, updatedAt: 2, error: null };

function fakeRequest(overrides: Partial<Record<string, (data: Record<string, unknown>) => Record<string, unknown>>> = {}) {
  const handlers: Record<string, (data: Record<string, unknown>) => Record<string, unknown>> = {
    "kit.listele": () => ({ ok: true, kitler: KITLER }),
    "kit.durum": (data) => data.gorev_id
      ? { ok: true, ...KAYIT, prompt: "Merhaba", result: "Bitti: rapor hazır." }
      : { ok: true, kayitlar: [KAYIT] },
    "kit.gonder": () => ({ ok: true, kitId: "kod", taskId: "t2", threadId: "th", status: "queued" }),
    ...overrides,
  };
  return vi.fn<KitRequest>(async (name, data) => handlers[name](data));
}

describe("KitSendDialog", () => {
  it("yanıt metnini seçilen Kit'e görev olarak gönderir ve makbuzu gösterir", async () => {
    const request = fakeRequest();
    render(<KitSendDialog initialText="Bu raporu özetle" onClose={vi.fn()} request={request} />);
    expect(await screen.findByRole("option", { name: "Kod" })).toBeTruthy();
    expect((screen.getByLabelText("Gönderilecek metin") as HTMLTextAreaElement).value).toBe("Bu raporu özetle");
    fireEvent.change(screen.getByLabelText("Başlık (isteğe bağlı)"), { target: { value: "Özet" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Kit'e gönder" })));
    expect(request).toHaveBeenCalledWith("kit.gonder", { kit: "kod", metin: "Bu raporu özetle", tur: "gorev", baslik: "Özet" });
    expect((await screen.findByText(/«Kod» Kit'inin gelen kutusuna kuyruğa alındı/)).textContent).toContain("sırası gelince");
    // Gönderimden sonra gelen kutusu yenilenir.
    expect(request.mock.calls.filter(([name, data]) => name === "kit.durum" && !data.gorev_id).length).toBeGreaterThanOrEqual(2);
  });

  it("mesaj türü seçilebilir", async () => {
    const request = fakeRequest();
    render(<KitSendDialog initialText="Selam Kit" onClose={vi.fn()} request={request} />);
    await screen.findByRole("option", { name: "Kod" });
    fireEvent.click(screen.getByRole("radio", { name: "Mesaj" }));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Kit'e gönder" })));
    expect(request).toHaveBeenCalledWith("kit.gonder", { kit: "kod", metin: "Selam Kit", tur: "mesaj" });
  });

  it("Fusion izni kapalı Kit'e gönderimi kapatır ve ayarın yerini söyler", async () => {
    const request = fakeRequest();
    render(<KitSendDialog initialText="Bu raporu özetle" onClose={vi.fn()} request={request} />);
    await screen.findByRole("option", { name: "Kapalı (Fusion izni kapalı)" });
    fireEvent.change(screen.getByLabelText("Kit"), { target: { value: "kapali" } });
    expect(screen.getByText(/Kit'i düzenle > Fusion iznini aç/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "Kit'e gönder" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("kısa metni göndermeden reddeder", async () => {
    const request = fakeRequest();
    render(<KitSendDialog initialText="ab" onClose={vi.fn()} request={request} />);
    await screen.findByRole("option", { name: "Kod" });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Kit'e gönder" })));
    expect((await screen.findByRole("alert")).textContent).toBe("Metin en az 3 karakter olmalı.");
    expect(request.mock.calls.some(([name]) => name === "kit.gonder")).toBe(false);
  });

  it("Kits ulaşılmazsa Türkçe nedeni gösterir", async () => {
    const request = fakeRequest({ "kit.listele": () => ({ ok: false, metin: "Kits çalışmıyor (http://127.0.0.1:4410)." }) });
    render(<KitSendDialog initialText="Bu raporu özetle" onClose={vi.fn()} request={request} />);
    expect((await screen.findByRole("alert")).textContent).toContain("Kits çalışmıyor");
    expect((screen.getByRole("button", { name: "Kit'e gönder" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("gelen kutusunu Türkçe durumla listeler, kayıt açılınca sonucu gösterir", async () => {
    const request = fakeRequest();
    render(<KitSendDialog initialText="Bu raporu özetle" onClose={vi.fn()} request={request} />);
    const kayit = await screen.findByRole("button", { name: /Fusion'dan görev.*Tamamlandı/ });
    await act(async () => fireEvent.click(kayit));
    expect(request).toHaveBeenCalledWith("kit.durum", { kit: "kod", gorev_id: "t1" });
    expect((await screen.findByText("Bitti: rapor hazır.")).tagName).toBe("PRE");
  });

  it("Escape ile kapanır", async () => {
    const onClose = vi.fn();
    render(<KitSendDialog initialText="Bu raporu özetle" onClose={onClose} request={fakeRequest()} />);
    await screen.findByRole("option", { name: "Kod" });
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });
});

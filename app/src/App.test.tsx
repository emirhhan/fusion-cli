import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionUygulama, Uygulama } from "./App";
import { ProtocolClient } from "./protocol/client";
import type { SessionTransport } from "./sessions/types";

function fakeClient() {
  let listener: ((line: string) => void) | null = null;
  const written: string[] = [];
  const client = new ProtocolClient(
    (line) => written.push(line),
    (handler) => {
      listener = handler;
    },
  );
  return { client, written, receive: (line: string) => listener?.(line) };
}

afterEach(() => {
  cleanup();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("Uygulama", () => {
  it("soru gelince onay diyaloğunu açar", async () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    fake.receive(JSON.stringify({
      tip: "soru",
      id: "1",
      veri: { tur: "onay", arac: "write_file", argumanlar: {}, secenekler: [{ deger: "deny", etiket: "Reddet" }] },
    }));
    await waitFor(() => expect(screen.getByText(/izin verilsin mi/i)).toBeTruthy());
  });

  it("olayları konuşma akışında gösterir", async () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    fake.receive(JSON.stringify({ tip: "olay", veri: { olay: "ToolExecuted", name: "write_file" } }));
    await waitFor(() => expect(screen.getByText(/write_file/)).toBeTruthy());
  });

  it("görevi tur.calistir isteğiyle gönderir", () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "bir oyun yap" } });
    screen.getByRole("button", { name: "Gönder" }).click();
    const request = fake.written.map((line) => JSON.parse(line)).find((message) => message.ad === "tur.calistir");
    expect(request?.veri).toEqual({ gorev: "bir oyun yap" });
  });

  it("çalışan görevi kanonik tur.kes isteğiyle durdurur", () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Mesaj" }), {
      target: { value: "uzun görev" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));
    fireEvent.click(screen.getByRole("button", { name: "Durdur" }));
    expect(fake.written.map((line) => JSON.parse(line)).some((message) => message.ad === "tur.kes")).toBe(
      true,
    );
  });

  it("profesyonel kabuğun tüm ana yüzeylerini bağlar", () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    expect(screen.getByRole("navigation", { name: "Ana navigasyon" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Yeni görev" })).toBeTruthy();
    expect(screen.getByRole("complementary", { name: "Denetçi" })).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Mesaj" })).toBeTruthy();
  });

  it("tema seçimini belgeye uygular ve saklar", () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Tema" }), {
      target: { value: "dark" },
    });
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("fusion.theme")).toBe("dark");
  });

  it("başlangıç önerisini görev girişine taşır", () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    fireEvent.click(screen.getByRole("button", { name: "Yeni bir web projesi oluştur" }));
    expect(screen.getByRole("textbox", { name: "Mesaj" })).toHaveProperty(
      "value",
      "Yeni bir web projesi oluştur",
    );
  });
});

describe("SessionUygulama", () => {
  it("aktif projenin dosya ağacını açar ve seçilen metni gösterir", async () => {
    let lineHandler: ((event: { oturum_id: string; satir: string }) => void) | null = null;
    const transport: SessionTransport = {
      create: vi.fn(async (id) => ({
        oturum_id: id,
        kok: "/proje",
        pid: 41,
        durum: "calisiyor",
        kapanis_nedeni: null,
      })),
      send: vi.fn(async (id, line) => {
        const request = JSON.parse(line) as { id: string; ad: string; veri: Record<string, unknown> };
        let veri: Record<string, unknown> = { ok: true };
        if (request.ad === "gecmis.kaynaklar") veri = { ok: true, kaynaklar: [] };
        if (request.ad === "proje.durum") {
          veri = { ok: true, kok: "/proje", git: true, okunabilir: true, yazilabilir: true };
        }
        if (request.ad === "proje.listele" && request.veri.yol === "") {
          veri = {
            ok: true,
            yol: "",
            girdiler: [
              { ad: "src", yol: "src", tur: "klasor", boyut: 0, degistirilme: 10 },
            ],
            next_cursor: null,
            has_more: false,
          };
        }
        if (request.ad === "proje.listele" && request.veri.yol === "src") {
          veri = {
            ok: true,
            yol: "src",
            girdiler: [
              { ad: "main.py", yol: "src/main.py", tur: "dosya", boyut: 15, degistirilme: 11 },
            ],
            next_cursor: null,
            has_more: false,
          };
        }
        if (request.ad === "proje.oku") {
          veri = {
            ok: true,
            yol: "src/main.py",
            tur: "metin",
            mime: "text/x-python",
            boyut: 15,
            sha256: "abc",
            icerik: "print('Fusion')",
            kesildi: false,
          };
        }
        if (request.ad === "proje.yaz") {
          veri = {
            ok: true,
            yol: "src/main.py",
            sha256: "def",
            diff: "--- a/src/main.py\n+++ b/src/main.py\n-print('Fusion')\n+print('Fusion App')",
            added: 1,
            removed: 1,
          };
        }
        if (request.ad === "proje.degisiklikler") {
          veri = {
            ok: true,
            degisiklikler: [{
              yol: "src/main.py",
              diff: "--- a/src/main.py\n+++ b/src/main.py\n-print('Fusion')\n+print('Fusion App')",
              added: 1,
              removed: 1,
              geri_alinabilir: true,
            }],
          };
        }
        queueMicrotask(() => lineHandler?.({
          oturum_id: id,
          satir: JSON.stringify({ tip: "sonuc", id: request.id, veri }),
        }));
      }),
      close: vi.fn(async () => undefined),
      list: vi.fn(async () => []),
      onLine: vi.fn(async (handler) => {
        lineHandler = handler;
        return () => undefined;
      }),
      onClosed: vi.fn(async () => () => undefined),
    };

    render(<SessionUygulama transport={transport} />);

    fireEvent.click(await screen.findByRole("treeitem", { name: "src" }));
    fireEvent.click(await screen.findByRole("treeitem", { name: "main.py" }));
    expect(await screen.findByText("print('Fusion')")).toBeTruthy();
    expect(screen.getByText("src/main.py")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Düzenle" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Dosya içeriği" }), {
      target: { value: "print('Fusion App')" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    await waitFor(() => {
      const calls = vi.mocked(transport.send).mock.calls.map(([, line]) => JSON.parse(line));
      expect(calls.some((request) => request.ad === "proje.yaz" &&
        request.veri.expected_sha256 === "abc")).toBe(true);
    });

    fireEvent.click(screen.getByRole("tab", { name: "Değişiklikler" }));
    expect(await screen.findByText("+print('Fusion App')")).toBeTruthy();
  });

  it("yeni konuşma açar ve aktif konuşmanın kendi mesajlarını gösterir", async () => {
    const transport: SessionTransport = {
      create: vi.fn(async (id) => ({
        oturum_id: id,
        kok: "/proje",
        pid: id === "varsayilan" ? 41 : 42,
        durum: "calisiyor",
        kapanis_nedeni: null,
      })),
      send: vi.fn(async () => undefined),
      close: vi.fn(async () => undefined),
      list: vi.fn(async () => []),
      onLine: vi.fn(async () => () => undefined),
      onClosed: vi.fn(async () => () => undefined),
    };
    render(<SessionUygulama transport={transport} />);
    await screen.findByRole("heading", { name: "Yeni görev" });

    fireEvent.change(screen.getByRole("textbox", { name: "Mesaj" }), {
      target: { value: "ilk görev" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));
    await waitFor(() => expect(screen.getAllByText("ilk görev").length).toBeGreaterThan(1));
    fireEvent.click(screen.getByRole("button", { name: "Yeni görev" }));

    await waitFor(() => expect(transport.create).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("heading", { name: "Yeni görev" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "ilk görev" }));
    expect(screen.getByRole("heading", { name: "ilk görev" })).toBeTruthy();
    expect(screen.getAllByText("ilk görev").length).toBeGreaterThan(1);
  });

  it("keşfedilen geçmiş kaynağını sidebar ve seçiciye bağlar", async () => {
    let lineHandler: ((event: { oturum_id: string; satir: string }) => void) | null = null;
    const transport: SessionTransport = {
      create: vi.fn(async (id) => ({
        oturum_id: id,
        kok: "/proje",
        pid: 41,
        durum: "calisiyor",
        kapanis_nedeni: null,
      })),
      send: vi.fn(async (id, line) => {
        const request = JSON.parse(line) as { id: string; ad: string };
        const veri = request.ad === "gecmis.kaynaklar"
          ? { ok: true, kaynaklar: [{ ad: "claude", komut: "/resumeclaude" }] }
          : request.ad === "gecmis.oturumlar"
            ? {
                ok: true,
                kaynak: "claude",
                oturumlar: [{
                  kaynak: "claude",
                  oturum_id: "c1",
                  baslik: "Eski oyun konuşması",
                  guncellendi: 100,
                  tur_sayisi: 2,
                  boyut: 100,
                }],
                next_cursor: null,
                has_more: false,
              }
            : { ok: true };
        queueMicrotask(() => lineHandler?.({
          oturum_id: id,
          satir: JSON.stringify({ tip: "sonuc", id: request.id, veri }),
        }));
      }),
      close: vi.fn(async () => undefined),
      list: vi.fn(async () => []),
      onLine: vi.fn(async (handler) => {
        lineHandler = handler;
        return () => undefined;
      }),
      onClosed: vi.fn(async () => () => undefined),
    };
    render(<SessionUygulama transport={transport} />);

    fireEvent.click(await screen.findByRole("button", { name: "Claude geçmişi" }));
    expect(await screen.findByRole("dialog", { name: "Bir konuşma seçin" })).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Eski oyun konuşması" })).toBeTruthy();
  });
});

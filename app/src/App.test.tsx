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

  it("kayıtlı temayı belgeye uygular ve ana ekranda seçici çizmez", () => {
    // Tema değiştirme Ayarlar ekranına taşındı; ana ekranda yalnız UYGULANIR.
    localStorage.setItem("fusion.theme", "dark");
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.queryByRole("combobox", { name: "Tema" })).toBeNull();
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
  it("yerel seçiciden alınan klasörde kod görevi açar; iptalde oturum oluşturmaz", async () => {
    const transport: SessionTransport = {
      create: vi.fn(async (id, root) => ({
        oturum_id: id,
        kok: root ?? "/Users/test",
        pid: 41,
        durum: "calisiyor",
        kapanis_nedeni: null,
      })),
      send: vi.fn(async () => undefined),
      close: vi.fn(async () => undefined),
      list: vi.fn(async () => []),
      onLine: vi.fn(async () => () => undefined),
      onClosed: vi.fn(async () => () => undefined),
    };
    const selectFolder = vi.fn()
      .mockResolvedValueOnce("/Users/test/Desktop/Oyun")
      .mockResolvedValueOnce(null);

    render(<SessionUygulama selectFolder={selectFolder} transport={transport} />);
    await screen.findByRole("heading", { name: "Yeni görev" });

    fireEvent.click(screen.getAllByRole("button", { name: "Yeni görev" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Klasörde kod görevi" }));
    await waitFor(() => expect(transport.create).toHaveBeenCalledTimes(2));
    expect(vi.mocked(transport.create).mock.calls[1][1]).toBe("/Users/test/Desktop/Oyun");
    expect(localStorage.getItem("fusion.last-project-root")).toBe("/Users/test/Desktop/Oyun");

    fireEvent.click(screen.getAllByRole("button", { name: "Yeni görev" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Klasörde kod görevi" }));
    await waitFor(() => expect(selectFolder).toHaveBeenCalledTimes(2));
    expect(transport.create).toHaveBeenCalledTimes(2);
    expect(selectFolder).toHaveBeenLastCalledWith("/Users/test/Desktop/Oyun");
  });

  it("aktif projenin dosya ağacını açar ve seçilen metni gösterir", async () => {
    let lineHandler: ((event: { oturum_id: string; satir: string }) => void) | null = null;
    let processStarted = false;
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
        if (request.ad === "surec.baslat") {
          processStarted = true;
          veri = {
            ok: true,
            surec_id: "surec-1",
            komut: request.veri.komut,
            cwd: ".",
            pid: 99,
            durum: "bitti",
            cikis_kodu: 0,
            cikti: "testler geçti",
            baslangic: 10,
          };
        }
        if (request.ad === "surec.listele") {
          veri = {
            ok: true,
            surecler: processStarted ? [{
              surec_id: "surec-1",
              komut: "npm test",
              cwd: ".",
              pid: 99,
              durum: "bitti",
              cikis_kodu: 0,
              cikti: "testler geçti",
              baslangic: 10,
            }] : [],
          };
        }
        if (request.ad === "proje.komut_onerileri") {
          veri = {
            ok: true,
            komutlar: [{ tur: "test", ad: "Testleri çalıştır", komut: "npm test" }],
          };
        }
        if (request.ad === "proje.git_durum") {
          veri = { ok: true, git: true, branch: "main", degisen: 1, ileride: 0, geride: 0 };
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

    fireEvent.click(screen.getByRole("tab", { name: "Terminal" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "Terminal komutu" }), {
      target: { value: "npm test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Çalıştır" }));
    expect(await screen.findByText("testler geçti")).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "Süreçler" }));
    expect(await screen.findByText("npm test")).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "Testler" }));
    expect(await screen.findByText("main")).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Testleri çalıştır" }));
    expect(await screen.findByText("testler geçti")).toBeTruthy();
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
    fireEvent.click(screen.getAllByRole("button", { name: "Yeni görev" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Sohbet başlat" }));

    await waitFor(() => expect(transport.create).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("heading", { name: "Yeni görev" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "ilk görev" }));
    expect(screen.getByRole("heading", { name: "ilk görev" })).toBeTruthy();
    expect(screen.getAllByText("ilk görev").length).toBeGreaterThan(1);
  });

  it("sol navigasyondan native beceri ve ajan kataloğunu açar", async () => {
    let lineHandler: ((event: { oturum_id: string; satir: string }) => void) | null = null;
    const transport: SessionTransport = {
      create: vi.fn(async (id) => ({ oturum_id: id, kok: "/proje", pid: 41, durum: "calisiyor", kapanis_nedeni: null })),
      send: vi.fn(async (_id, line) => {
        const request = JSON.parse(line);
        if (request.ad !== "yetenek.katalog") return;
        queueMicrotask(() => lineHandler?.({ oturum_id: "varsayilan", satir: JSON.stringify({ tip: "sonuc", id: request.id, veri: { ok: true, beceriler: [], ajanlar: [], talimatlar: [], mcp: [] } }) }));
      }),
      close: vi.fn(async () => undefined),
      list: vi.fn(async () => []),
      onLine: vi.fn(async (handler) => { lineHandler = handler; return () => undefined; }),
      onClosed: vi.fn(async () => () => undefined),
    };
    render(<SessionUygulama transport={transport} />);
    fireEvent.click(await screen.findByRole("button", { name: "Beceriler ve Ajanlar" }));
    expect(await screen.findByRole("heading", { name: "Beceriler ve Ajanlar", level: 1 })).toBeTruthy();
    expect(screen.queryByPlaceholderText("Fusion'a bir görev ver")).toBeNull();
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

    const composer = await screen.findByRole("textbox", { name: "Mesaj" });
    fireEvent.change(composer, { target: { value: "/res" } });
    expect(await screen.findByRole("option", { name: /resumeclaude/ })).toBeTruthy();
    expect(screen.queryByRole("option", { name: /resumehermes/ })).toBeNull();
    fireEvent.keyDown(composer, { key: "Enter" });
    fireEvent.keyDown(composer, { key: "Enter" });
    expect(await screen.findByRole("dialog", { name: "Bir konuşma seçin" })).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Eski oyun konuşması" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Kapat" }));

    fireEvent.click(await screen.findByRole("button", { name: "Claude geçmişi" }));
    expect(await screen.findByRole("dialog", { name: "Bir konuşma seçin" })).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Eski oyun konuşması" })).toBeTruthy();
  });
});

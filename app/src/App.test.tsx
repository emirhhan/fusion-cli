import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SessionUygulama, Uygulama } from "./App";
import { ProtocolClient } from "./protocol/client";
import type { SessionTransport } from "./sessions/types";
import type { PermissionBridge } from "./permissions/types";

const nativeDrops = vi.hoisted(() => {
  const state: { handler: ((paths: string[]) => void) | null } = { handler: null };
  const unlisten = vi.fn();
  const listen = vi.fn(async (handler: (paths: string[]) => void) => {
    state.handler = handler;
    return unlisten;
  });
  return { listen, state, unlisten };
});
const nativeInvoke = vi.hoisted(() => vi.fn(async (command: string) => {
  if (command.startsWith("izin_")) return { state: "granted", supported: true };
  if (command === "terminal_ac") return { terminalId: "terminal-1", cwd: "/proje", cols: 80, rows: 24, pid: 77 };
  return undefined;
}));

vi.mock("./platform/drop", () => ({ listenForFileDrops: nativeDrops.listen }));
vi.mock("@tauri-apps/api/core", () => ({ invoke: nativeInvoke }));
vi.mock("@tauri-apps/api/path", () => ({ desktopDir: vi.fn(async () => "/Users/test/Desktop") }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn(async () => vi.fn()) }));
vi.mock("./processes/XtermSession", () => ({
  XtermSession: ({ session }: { session: { snapshot: { terminalId: string } } }) => (
    <div>PTY {session.snapshot.terminalId}</div>
  ),
}));

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

function composerTransport(responses: Record<string, Record<string, unknown>> = {}) {
  let lineHandler: ((event: { oturum_id: string; satir: string }) => void) | null = null;
  const requests: Array<{ ad: string; id: string; veri: Record<string, unknown> }> = [];
  const transport: SessionTransport = {
    create: vi.fn(async (id) => ({
      oturum_id: id,
      kok: "/proje",
      pid: 41,
      durum: "calisiyor",
      kapanis_nedeni: null,
    })),
    send: vi.fn(async (id, line) => {
      const request = JSON.parse(line) as { ad: string; id: string; veri: Record<string, unknown> };
      requests.push(request);
      queueMicrotask(() => lineHandler?.({
        oturum_id: id,
        satir: JSON.stringify({
          tip: "sonuc",
          id: request.id,
          veri: responses[request.ad] ?? { ok: true },
        }),
      }));
    }),
    close: vi.fn(async () => undefined),
    list: vi.fn(async () => []),
    onLine: vi.fn(async (handler) => { lineHandler = handler; return () => undefined; }),
    onClosed: vi.fn(async () => () => undefined),
  };
  return { requests, transport };
}

afterEach(() => {
  cleanup();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  nativeDrops.state.handler = null;
  nativeDrops.listen.mockClear();
  nativeDrops.unlisten.mockClear();
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
  it("yalnız etkin MCP satırını önerir; tıklama inputu doldurur, Enter komutu yürütür", async () => {
    const fake = composerTransport({
      "gecmis.kaynaklar": { ok: true, kaynaklar: [] },
      "komut.listele": {
        ok: true,
        komutlar: [{ ad: "resumehermes", aciklama: "Ham resume", grup: "Geçmiş" }],
      },
      "yetenek.katalog": {
        ok: true,
        mcp: [
          { ad: "github", aciklama: "GitHub araçları", etkin: true },
          { ad: "kapali", aciklama: "Kapalı araç", etkin: false },
          { ad: "belirsiz", aciklama: "Etkinliği belirsiz araç" },
        ],
      },
      "komut.calistir": { ok: true, metin: "MCP hazır" },
    });
    render(<SessionUygulama transport={fake.transport} />);

    const textbox = await screen.findByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "/mcp" } });
    const github = await screen.findByRole("option", { name: /mcp github.*GitHub araçları/i });
    expect(screen.queryByRole("option", { name: /mcp kapali/i })).toBeNull();
    expect(screen.queryByRole("option", { name: /mcp belirsiz/i })).toBeNull();
    expect(screen.queryByRole("option", { name: /resumehermes/i })).toBeNull();

    fireEvent.click(github);
    expect(textbox).toHaveProperty("value", "/mcp github");
    expect(fake.requests.some((request) => request.ad === "komut.calistir")).toBe(false);

    fireEvent.keyDown(textbox, { key: "Enter" });
    await waitFor(() => expect(fake.requests.some((request) =>
      request.ad === "komut.calistir" && request.veri.ad === "mcp" && request.veri.arguman === "github",
    )).toBe(true));
  });

  it("ataç seçicisinin keyfi proje dosyasını ve görseli chip olarak gönderir", async () => {
    const fake = composerTransport({ "gecmis.kaynaklar": { ok: true, kaynaklar: [] } });
    const selectFiles = vi.fn().mockResolvedValue([
      "/proje/model.weights-custom",
      "/proje/referans.png",
    ]);
    render(<SessionUygulama selectFiles={selectFiles} transport={fake.transport} />);

    fireEvent.click(await screen.findByRole("button", { name: "Dosya veya klasör ekle" }));
    expect(await screen.findByText("model.weights-custom")).toBeTruthy();
    expect(await screen.findByText("referans.png")).toBeTruthy();
    expect(selectFiles).toHaveBeenCalledWith("/proje");

    const textbox = screen.getByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "Bu dosyaları incele" } });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));
    await waitFor(() => expect(fake.requests.some((request) =>
      request.ad === "tur.calistir" && JSON.stringify(request.veri.ekler) === JSON.stringify([
        { kind: "file", name: "model.weights-custom", path: "/proje/model.weights-custom" },
        { kind: "image", name: "referans.png", path: "/proje/referans.png" },
      ]),
    )).toBe(true));
  });

  it("native ve browser drop yollarını aynı ek chiplerinde gösterir", async () => {
    const fake = composerTransport({ "gecmis.kaynaklar": { ok: true, kaynaklar: [] } });
    const { container } = render(<SessionUygulama transport={fake.transport} />);
    await screen.findByRole("textbox", { name: "Mesaj" });
    await waitFor(() => expect(nativeDrops.state.handler).not.toBeNull());

    act(() => nativeDrops.state.handler?.(["/proje/native.data"]));
    expect(await screen.findByText("native.data")).toBeTruthy();

    const image = new File(["png"], "browser.png", { type: "image/png" });
    Object.defineProperty(image, "path", { value: "/proje/browser.png" });
    fireEvent.drop(container.querySelector(".composer")!, { dataTransfer: { files: [image] } });
    expect(await screen.findByText("browser.png")).toBeTruthy();

    const textbox = screen.getByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "Drop dosyalarını incele" } });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));
    await waitFor(() => expect(fake.requests.some((request) =>
      request.ad === "tur.calistir" && JSON.stringify(request.veri.ekler) === JSON.stringify([
        { kind: "file", name: "native.data", path: "/proje/native.data" },
        { kind: "image", name: "browser.png", path: "/proje/browser.png" },
      ]),
    )).toBe(true));
  });

  it("dosya seçici hatasını ek alanında gösterir", async () => {
    const fake = composerTransport({ "gecmis.kaynaklar": { ok: true, kaynaklar: [] } });
    const selectFiles = vi.fn().mockRejectedValue(new Error("selector kapalı"));
    render(<SessionUygulama selectFiles={selectFiles} transport={fake.transport} />);

    fireEvent.click(await screen.findByRole("button", { name: "Dosya veya klasör ekle" }));
    expect(await screen.findByText(/dosya seçici açılamadı/i)).toBeTruthy();
  });

  it("native drop kurulumu hatasını ek alanında gösterir", async () => {
    const fake = composerTransport({ "gecmis.kaynaklar": { ok: true, kaynaklar: [] } });
    nativeDrops.listen.mockRejectedValueOnce(new Error("drop listener kapalı"));
    render(<SessionUygulama transport={fake.transport} />);

    expect(await screen.findByText(/sürükle.*dinleyicisi.*başlatılamadı/i)).toBeTruthy();
  });

  it("seçicinin boş path sonucunu ek alanında gösterir", async () => {
    const fake = composerTransport({ "gecmis.kaynaklar": { ok: true, kaynaklar: [] } });
    const selectFiles = vi.fn().mockResolvedValue(["", "   "]);
    render(<SessionUygulama selectFiles={selectFiles} transport={fake.transport} />);

    fireEvent.click(await screen.findByRole("button", { name: "Dosya veya klasör ekle" }));
    expect(await screen.findByText(/geçerli bir dosya yolu/i)).toBeTruthy();
    expect(screen.queryByLabelText("Ekler")).toBeNull();
  });

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

    fireEvent.click(screen.getByRole("button", { name: /Proje seç:/ }));
    fireEvent.click(screen.getByRole("button", { name: "Yeni proje / klasör seç" }));
    fireEvent.click(screen.getByRole("button", { name: /Devam et/i }));
    await waitFor(() => expect(transport.create).toHaveBeenCalledTimes(2));
    expect(vi.mocked(transport.create).mock.calls[1][1]).toBe("/Users/test/Desktop/Oyun");
    expect(localStorage.getItem("fusion.last-project-root")).toBe("/Users/test/Desktop/Oyun");

    fireEvent.click(screen.getByRole("button", { name: /Proje seç:/ }));
    fireEvent.click(screen.getByRole("button", { name: "Yeni proje / klasör seç" }));
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
    fireEvent.click(await screen.findByRole("button", { name: "Yeni terminal" }));
    await waitFor(() => expect(nativeInvoke).toHaveBeenCalledWith("terminal_ac", {
      cwd: "/proje", cols: 80, rows: 24,
    }));
    expect(await screen.findByText("PTY terminal-1")).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "Testler" }));
    expect(await screen.findByText("main")).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Testleri çalıştır" }));
    expect(await screen.findByText("testler geçti")).toBeTruthy();

    fireEvent.click(screen.getByRole("tab", { name: "Süreçler" }));
    expect(await screen.findByText("npm test")).toBeTruthy();
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
    fireEvent.click(screen.getByRole("button", { name: "Yeni sohbet" }));

    await waitFor(() => expect(transport.create).toHaveBeenCalledTimes(2));
    expect(vi.mocked(transport.create).mock.calls[1][1]).toBe("/Users/test/Desktop");
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
    fireEvent.click(await screen.findByRole("button", { name: "Emir profil menüsü" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Beceriler ve Ajanlar" }));
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

describe("Sohbetten çalışma klasörü", () => {
  it("/klasor komutu klasör seçiciyi açar ve seçilen kökte çalışır", async () => {
    const transport: SessionTransport = {
      create: vi.fn(async (id: string, root?: string) => ({
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
    const selectFolder = vi.fn().mockResolvedValue("/Users/test/Desktop/Fusion");
    const permissionBridge: PermissionBridge = {
      request: vi.fn().mockResolvedValueOnce("denied").mockResolvedValueOnce("granted"),
      openSettings: vi.fn(),
    };
    render(<SessionUygulama permissionBridge={permissionBridge} selectFolder={selectFolder} transport={transport} />);

    const alan = await screen.findByRole("textbox", { name: "Mesaj" });
    fireEvent.change(alan, { target: { value: "/klasor" } });
    // İlk Enter paletten komutu seçer, ikincisi gönderir.
    fireEvent.keyDown(alan, { key: "Enter" });
    fireEvent.keyDown(alan, { key: "Enter" });

    fireEvent.click(await screen.findByRole("button", { name: "Devam et" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Yeniden dene" })).toBeTruthy());
    expect(selectFolder).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));

    await waitFor(() => expect(selectFolder).toHaveBeenCalledOnce());
    await waitFor(() => expect(vi.mocked(transport.create).mock.calls.at(-1)?.[1]).toBe(
      "/Users/test/Desktop/Fusion",
    ));
    // Klasör değiştirme çekirdeğe komut olarak GİTMEZ: uygulama tarafı iştir.
    const gonderilenler = vi.mocked(transport.send).mock.calls.map(([, line]) => line);
    expect(gonderilenler.some((line) => line.includes("/klasor"))).toBe(false);
  });

  it("/klasor komut listesinde görünür", async () => {
    const transport: SessionTransport = {
      create: vi.fn(async (id: string, root?: string) => ({
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
    render(<SessionUygulama selectFolder={vi.fn()} transport={transport} />);

    const alan = await screen.findByRole("textbox", { name: "Mesaj" });
    fireEvent.change(alan, { target: { value: "/klas" } });
    expect(await screen.findByRole("option", { name: /klasor/ })).toBeTruthy();
  });
});

describe("Çalışma kipi", () => {
  function modeTransport(fail: boolean): SessionTransport {
    let lineHandler: ((event: { oturum_id: string; satir: string }) => void) | null = null;
    return {
      create: vi.fn(async (id: string, root?: string) => ({
        oturum_id: id,
        kok: root ?? "/Users/test",
        pid: 41,
        durum: "calisiyor",
        kapanis_nedeni: null,
      })),
      send: vi.fn(async (id: string, line: string) => {
        const request = JSON.parse(line);
        const veri = request.ad === "oturum.baslat" && fail
          ? { ok: false, metin: "Kip değiştirilemedi." }
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
  }

  it("çekirdek kipi reddederse arayüz eski kipte kalır ve bunu söyler", async () => {
    render(<SessionUygulama transport={modeTransport(true)} />);
    await screen.findByRole("textbox", { name: "Mesaj" });

    fireEvent.click(screen.getByRole("button", { name: "Kod" }));

    await waitFor(() => expect(screen.getByText(/Kip değiştirilemedi/)).toBeTruthy());
    expect(screen.getByRole("button", { name: "Sohbet" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("çekirdek kabul ederse kod kipine geçer", async () => {
    render(<SessionUygulama transport={modeTransport(false)} />);
    await screen.findByRole("textbox", { name: "Mesaj" });

    fireEvent.click(screen.getByRole("button", { name: "Kod" }));

    await waitFor(() => expect(
      screen.getByRole("button", { name: "Kod" }).getAttribute("aria-pressed"),
    ).toBe("true"));
  });
});

it("son sohbet silinince yeni Desktop sohbeti açılabilir ve eski kimlik geri gelmez", async () => {
  const fake = composerTransport({ "sohbet.sil": { ok: true }, "sohbet.listele": { ok: true, sohbetler: [] } });
  render(<SessionUygulama transport={fake.transport} />);
  await screen.findByRole("heading", { name: "Yeni görev" });
  const deletedId = vi.mocked(fake.transport.create).mock.calls[0][0];
  fireEvent.click(screen.getByRole("button", { name: "Yeni görev sohbetini sabitle" }));
  fireEvent.click(screen.getByRole("button", { name: "Yeni görev sohbetini sil" }));
  await screen.findByRole("button", { name: "Desktop içinde yeni sohbet başlat" });
  await waitFor(() => expect(JSON.parse(localStorage.getItem("fusion.sidebar.pinned-sessions.v1")!)).toEqual([]));
  expect(screen.queryByText("Hazırlanıyor…")).toBeNull();
  expect(screen.queryByRole("button", { name: "Yeni görev sohbetini sil" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Yeni sohbet" }));
  await waitFor(() => expect(fake.transport.create).toHaveBeenCalledTimes(2));
  expect(vi.mocked(fake.transport.create).mock.calls[1][0]).not.toBe(deletedId);
  expect(vi.mocked(fake.transport.create).mock.calls[1][1]).toBe("/Users/test/Desktop");
  await screen.findByRole("textbox", { name: "Mesaj" });
});

it("boş shell oluşturma sayfalarını açar ve saklı sohbetleri siler", async () => {
  const fake = composerTransport({ "sohbet.sil": { ok: true }, "sohbet.listele": { ok: true, sohbetler: [{ sohbet_id: "sakli", baslik: "Saklı sohbet", kok: "/proje", guncelleme: 1, mesaj_sayisi: 1 }] } });
  render(<SessionUygulama transport={fake.transport} />);
  await screen.findByRole("button", { name: "Saklı sohbet" });
  fireEvent.click(screen.getByRole("button", { name: "Yeni görev sohbetini sil" }));
  await screen.findByRole("button", { name: "Desktop içinde yeni sohbet başlat" });
  fireEvent.click(screen.getByRole("button", { name: "Görsel oluştur" }));
  expect(screen.getByRole("heading", { name: "Görsel oluştur" })).toBeTruthy();
  expect(screen.getByText("Daha sonra")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Video oluştur" }));
  expect(screen.getByRole("heading", { name: "Video oluştur" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Saklı sohbet sohbetini sil" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Saklı sohbet" })).toBeNull());
  expect(fake.requests.some((request) => request.ad === "sohbet.sil" && request.veri.sohbet_id === "sakli")).toBe(true);
});

it("boş shell profil hedefi için yeni çekirdek açıp istenen sayfaya gider", async () => {
  const fake = composerTransport({ "sohbet.sil": { ok: true }, "sohbet.listele": { ok: true, sohbetler: [] } });
  render(<SessionUygulama transport={fake.transport} />);
  fireEvent.click(await screen.findByRole("button", { name: "Yeni görev sohbetini sil" }));
  await screen.findByRole("button", { name: "Desktop içinde yeni sohbet başlat" });
  fireEvent.click(screen.getByRole("button", { name: "Emir profil menüsü" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Ayarlar" }));
  await screen.findByRole("heading", { name: "Ayarlar" });
  expect(vi.mocked(fake.transport.create).mock.calls[1][1]).toBe("/Users/test/Desktop");
});

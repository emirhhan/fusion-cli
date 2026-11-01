import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  if (command === "terminal_ac_kanal") return { terminalId: "terminal-1", cwd: "/proje", cols: 80, rows: 24, pid: 77 };
  return undefined;
}));

vi.mock("./platform/drop", () => ({ listenForFileDrops: nativeDrops.listen }));
vi.mock("@tauri-apps/api/core", () => ({
  invoke: nativeInvoke,
  Channel: class { onmessage: (message: unknown) => void = () => undefined; },
}));
vi.mock("@tauri-apps/api/path", () => ({ desktopDir: vi.fn(async () => "/Users/test/Desktop") }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn(async () => vi.fn()) }));
vi.mock("./processes/XtermSession", () => ({
  XtermSession: ({ session }: { session: { snapshot: { terminalId: string } } }) => (
    <div>PTY {session.snapshot.terminalId}</div>
  ),
  // Gerçek ölçüm xterm'i ve bir tarayıcıyı gerektirir; jsdom'da varsayılana düşer.
  measureTerminalSize: () => ({ cols: 0, rows: 0 }),
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
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Dosya oluştur" } });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));
    fake.receive(JSON.stringify({ tip: "olay", veri: { olay: "ToolExecuted", name: "write_file" } }));
    await waitFor(() => expect(screen.getAllByText(/dosya yazılıyor/).length).toBeGreaterThan(0));
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
  it("opens a named project in its selected folder and + creates another chat there", async () => {
    localStorage.setItem("fusion.permission-explanations.v1", JSON.stringify({ workspace: true }));
    const fake = composerTransport({ "ayar.arayuz": { ok: true, degerler: {} } });
    vi.mocked(fake.transport.create).mockImplementation(async (id, root) => ({
      oturum_id: id, kok: root ?? "/Users/test/Desktop", pid: 41,
      durum: "calisiyor", kapanis_nedeni: null,
    }));
    render(<SessionUygulama transport={fake.transport} selectFolder={async () => "/work/blog"} />);
    fireEvent.click(await screen.findByRole("button", { name: "Yeni proje" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Proje adı" }), { target: { value: "Benim Blogum" } });
    fireEvent.click(screen.getByRole("button", { name: "Klasör seç" }));
    await screen.findByText("/work/blog");
    fireEvent.click(screen.getByRole("button", { name: "Oluştur" }));
    await screen.findByRole("button", { name: "Proje seç: Benim Blogum" });
    expect(vi.mocked(fake.transport.create).mock.calls.at(-1)?.[1]).toBe("/work/blog");
    const previousId = vi.mocked(fake.transport.create).mock.calls.at(-1)?.[0];
    fireEvent.click(screen.getByRole("button", { name: "Benim Blogum projesinde yeni sohbet başlat" }));
    await waitFor(() => expect(vi.mocked(fake.transport.create).mock.calls.at(-1)?.[0]).not.toBe(previousId));
    expect(vi.mocked(fake.transport.create).mock.calls.at(-1)?.[1]).toBe("/work/blog");
    expect(screen.getByRole("button", { name: "Proje seç: Benim Blogum" })).toBeTruthy();
  });

  it("reveals a project start failure and keeps the project for retry", async () => {
    localStorage.setItem("fusion.permission-explanations.v1", JSON.stringify({ workspace: true }));
    const fake = composerTransport({ "ayar.arayuz": { ok: true, degerler: {} } });
    vi.mocked(fake.transport.create).mockImplementation(async (id, root) => {
      if (root === "/missing") throw new Error("çalışma dizini bulunamadı: /missing");
      return { oturum_id: id, kok: "/Users/test/Desktop", pid: 41, durum: "calisiyor", kapanis_nedeni: null };
    });
    render(<SessionUygulama transport={fake.transport} selectFolder={async () => "/missing"} />);
    fireEvent.click(await screen.findByRole("button", { name: "Yeni proje" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Proje adı" }), { target: { value: "Tekrar dene" } });
    fireEvent.click(screen.getByRole("button", { name: "Klasör seç" }));
    await screen.findByText("/missing");
    fireEvent.click(screen.getByRole("button", { name: "Oluştur" }));
    const alert = await screen.findByText(/Proje kaydedildi fakat sohbet açılamadı/);
    expect(alert.closest('[hidden]')).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Tekrar dene projesinde yeni sohbet başlat" })).toBeTruthy();
  });
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

  it("! kabuk çıktısından sonra model turu kendiliğinden başlar (#219)", async () => {
    let calls = 0;
    const responses: Record<string, Record<string, unknown>> = {
      "gecmis.kaynaklar": { ok: true, kaynaklar: [] },
      get "tur.calistir"() {
        calls += 1;
        return calls === 1
          ? { ok: true, metin: "$ ls", yerel_yanit: true, gorev: "Kabuk çıktısına yanıt ver" }
          : { ok: true, metin: "Klasörde iki dosya var." };
      },
    };
    const fake = composerTransport(responses);
    render(<SessionUygulama transport={fake.transport} />);

    const textbox = await screen.findByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "! ls" } });
    fireEvent.keyDown(textbox, { key: "Enter" });
    await waitFor(() => expect(fake.requests.filter((request) => request.ad === "tur.calistir")
      .map((request) => request.veri.gorev)).toEqual(["! ls", "Kabuk çıktısına yanıt ver"]));
    expect(await screen.findByText("Klasörde iki dosya var.")).toBeTruthy();
  });

  it("tur biterken modele gitmemiş yönlendirme sıradaki tur olarak gider (#190)", async () => {
    let calls = 0;
    const responses: Record<string, Record<string, unknown>> = {
      "gecmis.kaynaklar": { ok: true, kaynaklar: [] },
      get "tur.calistir"() {
        calls += 1;
        return calls === 1
          ? { ok: true, metin: "İlk iş bitti.", kalan_yonlendirme: ["testleri de koştur"] }
          : { ok: true, metin: "Testler geçti." };
      },
    };
    const fake = composerTransport(responses);
    render(<SessionUygulama transport={fake.transport} />);

    const textbox = await screen.findByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "işi yap" } });
    fireEvent.keyDown(textbox, { key: "Enter" });
    await waitFor(() => expect(fake.requests.filter((request) => request.ad === "tur.calistir")
      .map((request) => request.veri.gorev)).toEqual(["işi yap", "testleri de koştur"]));
    expect(await screen.findByText("Testler geçti.")).toBeTruthy();
  });

  it("tur sürerken kuyruğa giren komut tur bitince çalışır (#209)", async () => {
    let calls = 0;
    const responses: Record<string, Record<string, unknown>> = {
      "gecmis.kaynaklar": { ok: true, kaynaklar: [] },
      get "komut.calistir"() {
        calls += 1;
        return calls === 1 ? { ok: true, metin: "", kuyruk: true } : { ok: true, metin: "Özetlendi." };
      },
    };
    const fake = composerTransport(responses);
    render(<SessionUygulama transport={fake.transport} />);

    const textbox = await screen.findByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "/compact" } });
    fireEvent.keyDown(textbox, { key: "Enter" });
    await waitFor(() => expect(fake.requests.filter((request) => request.ad === "komut.calistir")
      .map((request) => request.veri.kuyruktan === true)).toEqual([false, true]));
    expect(await screen.findByText("Özetlendi.")).toBeTruthy();
  });

  it("/rewind konuşmayı sarınca dönen istem giriş kutusuna konur (#200)", async () => {
    const fake = composerTransport({
      "gecmis.kaynaklar": { ok: true, kaynaklar: [] },
      "komut.calistir": { ok: true, metin: "Geri sarıldı.", girdi: "ikinci görev" },
    });
    render(<SessionUygulama transport={fake.transport} />);

    const textbox = await screen.findByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "/rewind 2 konusma" } });
    fireEvent.keyDown(textbox, { key: "Enter" });
    await waitFor(() => expect(fake.requests.some((request) =>
      request.ad === "komut.calistir" && request.veri.ad === "rewind",
    )).toBe(true));
    await waitFor(() =>
      expect(screen.getByRole("textbox", { name: "Mesaj" })).toHaveProperty("value", "ikinci görev"));
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
      .mockResolvedValueOnce("/Users/test/Desktop/VFS-BOT ")
      .mockResolvedValueOnce(null);

    render(<SessionUygulama selectFolder={selectFolder} transport={transport} />);
    await screen.findByRole("heading", { name: "Yeni görev" });

    fireEvent.click(screen.getByRole("button", { name: /Proje seç:/ }));
    fireEvent.click(screen.getByRole("button", { name: "Yeni proje / klasör seç" }));
    fireEvent.click(screen.getByRole("button", { name: /Devam et/i }));
    await waitFor(() => expect(transport.create).toHaveBeenCalledTimes(2));
    expect(vi.mocked(transport.create).mock.calls[1][1]).toBe("/Users/test/Desktop/VFS-BOT ");
    expect(localStorage.getItem("fusion.last-project-root")).toBe("/Users/test/Desktop/VFS-BOT ");

    fireEvent.click(screen.getByRole("button", { name: /Proje seç:/ }));
    fireEvent.click(screen.getByRole("button", { name: "Yeni proje / klasör seç" }));
    await waitFor(() => expect(selectFolder).toHaveBeenCalledTimes(2));
    expect(transport.create).toHaveBeenCalledTimes(2);
    expect(selectFolder).toHaveBeenLastCalledWith("/Users/test/Desktop/VFS-BOT ");
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
    await waitFor(() => expect(nativeInvoke).toHaveBeenCalledWith("terminal_ac_kanal", {
      cwd: "/proje", cols: 80, rows: 24, output: expect.anything(),
    }));
    expect(await screen.findByText("PTY terminal-1")).toBeTruthy();

    /* Doğrulama komutları artık DEĞİŞİKLİKLER sekmesinde: "ne değişti" ile
       "hâlâ çalışıyor mu" aynı soruya bakar. Ayrı Testler ve Süreçler
       sekmeleri git durumunu ve komut çıktısını ikinci kez gösteriyordu. */
    fireEvent.click(screen.getByRole("tab", { name: "Değişiklikler" }));
    expect(await screen.findByText("main")).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Testleri çalıştır" }));
    // Proje dosyalarından gelen komut ilk çalıştırmada onay ister (U4-49b).
    fireEvent.click(await screen.findByRole("button", { name: "Çalıştır" }));
    expect(await screen.findByText("testler geçti")).toBeTruthy();
    // Komut hem öneri düğmesinde hem kanıt dökümünde geçer; ikisi de beklenen.
    expect((await screen.findAllByText("npm test")).length).toBeGreaterThan(0);
  });

  it("yeni konuşma açar ve aktif konuşmanın kendi mesajlarını gösterir", async () => {
    let lineHandler: ((event: { oturum_id: string; satir: string }) => void) | null = null;
    const transport: SessionTransport = {
      create: vi.fn(async (id) => ({
        oturum_id: id,
        kok: "/proje",
        pid: id === "varsayilan" ? 41 : 42,
        durum: "calisiyor",
        kapanis_nedeni: null,
      })),
      // Yalnız başlık cevaplanır; tur bilerek açık kalır. Başlığı çekirdek verir.
      send: vi.fn(async (id, line) => {
        const request = JSON.parse(line);
        if (request.ad !== "sohbet.baslik") return;
        queueMicrotask(() => lineHandler?.({
          oturum_id: id,
          satir: JSON.stringify({ tip: "sonuc", id: request.id, veri: { ok: true, baslik: request.veri.metin } }),
        }));
      }),
      close: vi.fn(async () => undefined),
      list: vi.fn(async () => []),
      onLine: vi.fn(async (handler) => { lineHandler = handler; return () => undefined; }),
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
    expect(vi.mocked(transport.create).mock.calls[1][1]).toBe("/proje");
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
    fireEvent.click(await screen.findByRole("button", { name: "Hesap menüsü" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Beceriler ve Ajanlar" }));
    expect(await screen.findByRole("heading", { name: "Beceriler ve Ajanlar", level: 1 })).toBeTruthy();
    expect(screen.queryByPlaceholderText("Fusion'a bir görev ver")).toBeNull();
  });

  it.each([
    ["Hesabım", { role: "heading", name: "Hesabım" }, "Kapat"],
    ["Yardım", { role: "heading", name: "Yardım" }, "Kapat"],
    ["Kontrol Paneli", { role: "heading", name: "Kontrol Paneli" }, "Kapat"],
    ["Beceriler ve Ajanlar", { role: "heading", name: "Beceriler ve Ajanlar" }, "Kataloğu kapat"],
    ["MCP bağlantıları", { role: "heading", name: "Uygulamalar" }, "Kapat"],
  ] as const)("%s Ayarlar gibi tam sayfa açılır: sohbet kenar çubuğu gizlenir, Kapat önceki ekrana döner", async (etiket, hedef, kapat) => {
    let lineHandler: ((event: { oturum_id: string; satir: string }) => void) | null = null;
    const transport: SessionTransport = {
      create: vi.fn(async (id) => ({ oturum_id: id, kok: "/proje", pid: 41, durum: "calisiyor", kapanis_nedeni: null })),
      send: vi.fn(async (id, line) => {
        const request = JSON.parse(line) as { id: string };
        queueMicrotask(() => lineHandler?.({ oturum_id: id, satir: JSON.stringify({ tip: "sonuc", id: request.id, veri: { ok: true } }) }));
      }),
      close: vi.fn(async () => undefined),
      list: vi.fn(async () => []),
      onLine: vi.fn(async (handler) => { lineHandler = handler; return () => undefined; }),
      onClosed: vi.fn(async () => () => undefined),
    };
    render(<SessionUygulama transport={transport} />);
    await screen.findByRole("textbox", { name: "Mesaj" });
    const kenarCubugu = () => document.getElementById("fusion-sidebar");
    expect(kenarCubugu()?.hidden).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Hesap menüsü" }));
    fireEvent.click(screen.getByRole("menuitem", { name: etiket }));

    expect((await screen.findAllByRole(hedef.role, { name: hedef.name })).length).toBeGreaterThan(0);
    expect(kenarCubugu()?.hidden).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: kapat }));
    expect(await screen.findByRole("textbox", { name: "Mesaj" })).toBeTruthy();
    expect(kenarCubugu()?.hidden).toBe(false);
  });

  it.each(["Ayarlar", "Hesabım", "Kontrol Paneli"])("sol üstteki Home %s sayfasından sohbete döner", async (etiket) => {
    let lineHandler: ((event: { oturum_id: string; satir: string }) => void) | null = null;
    const transport: SessionTransport = {
      create: vi.fn(async (id) => ({ oturum_id: id, kok: "/proje", pid: 41, durum: "calisiyor", kapanis_nedeni: null })),
      send: vi.fn(async (id, line) => {
        const request = JSON.parse(line) as { id: string };
        queueMicrotask(() => lineHandler?.({ oturum_id: id, satir: JSON.stringify({ tip: "sonuc", id: request.id, veri: { ok: true } }) }));
      }),
      close: vi.fn(async () => undefined),
      list: vi.fn(async () => []),
      onLine: vi.fn(async (handler) => { lineHandler = handler; return () => undefined; }),
      onClosed: vi.fn(async () => () => undefined),
    };
    render(<SessionUygulama transport={transport} />);
    await screen.findByRole("textbox", { name: "Mesaj" });
    fireEvent.click(screen.getByRole("button", { name: "Hesap menüsü" }));
    fireEvent.click(screen.getByRole("menuitem", { name: etiket }));
    await waitFor(() => expect(screen.queryByRole("textbox", { name: "Mesaj" })).toBeNull());

    fireEvent.click(screen.getByRole("button", { name: "Home", exact: true }));
    expect(await screen.findByRole("textbox", { name: "Mesaj" })).toBeTruthy();
    expect(document.getElementById("fusion-sidebar")?.hidden).toBe(false);
  });

  it("Geri bildirim gönder sayfa değil pencere açar; sohbet ve kenar çubuğu yerinde kalır", async () => {
    let lineHandler: ((event: { oturum_id: string; satir: string }) => void) | null = null;
    const transport: SessionTransport = {
      create: vi.fn(async (id) => ({ oturum_id: id, kok: "/proje", pid: 41, durum: "calisiyor", kapanis_nedeni: null })),
      send: vi.fn(async (id, line) => {
        const request = JSON.parse(line) as { id: string };
        queueMicrotask(() => lineHandler?.({ oturum_id: id, satir: JSON.stringify({ tip: "sonuc", id: request.id, veri: { ok: true } }) }));
      }),
      close: vi.fn(async () => undefined),
      list: vi.fn(async () => []),
      onLine: vi.fn(async (handler) => { lineHandler = handler; return () => undefined; }),
      onClosed: vi.fn(async () => () => undefined),
    };
    render(<SessionUygulama transport={transport} />);
    await screen.findByRole("textbox", { name: "Mesaj" });

    fireEvent.click(screen.getByRole("button", { name: "Hesap menüsü" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Geri bildirim gönder" }));

    expect(await screen.findByRole("dialog", { name: "Geri bildirim gönder" })).toBeTruthy();
    expect(document.getElementById("fusion-sidebar")?.hidden).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Pencereyi kapat" }));
    expect(screen.queryByRole("dialog", { name: "Geri bildirim gönder" })).toBeNull();
    expect(screen.getByRole("textbox", { name: "Mesaj" })).toBeTruthy();
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
    expect(await screen.findByRole("button", { name: /Eski oyun konuşması/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Kapat" }));

    fireEvent.click(screen.getByRole("button", { name: /Diğer ajanlar/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Claude geçmişi" }));
    expect(await screen.findByRole("dialog", { name: "Bir konuşma seçin" })).toBeTruthy();
    expect(await screen.findByRole("button", { name: /Eski oyun konuşması/ })).toBeTruthy();
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

// Faz 5, Görev 5 ("tek kutu"): manuel Sohbet/Kod kip düğmesi ve çekirdeğe
// `oturum.baslat`la `kip` gönderen akış kaldırıldı — çekirdek artık her zaman
// `kod` (tam yetenek) varsayılanıyla başlıyor (bkz. `appserver/session.py`).
// Bu describe'ın testleri kaldırılmış düğmeleri tıklıyordu, silindi.

it("son sohbet silinince yeni Desktop sohbeti açılabilir ve eski kimlik geri gelmez", async () => {
  const fake = composerTransport({ "sohbet.sil": { ok: true }, "sohbet.listele": { ok: true, sohbetler: [] } });
  render(<SessionUygulama transport={fake.transport} />);
  await screen.findByRole("heading", { name: "Yeni görev" });
  const deletedId = vi.mocked(fake.transport.create).mock.calls[0][0];
  fireEvent.click(screen.getByRole("button", { name: "Yeni görev sohbet seçenekleri" }));
  fireEvent.click(screen.getByRole("menuitemcheckbox", { name: "Sabitle" }));
  fireEvent.click(screen.getByRole("button", { name: "Yeni görev sohbet seçenekleri" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Sil" }));
  fireEvent.click(screen.getByRole("button", { name: "Kalıcı olarak sil" }));
  await screen.findByRole("button", { name: "Desktop içinde yeni sohbet başlat" });
  await waitFor(() => expect(JSON.parse(localStorage.getItem("fusion.sidebar.pinned-sessions.v1")!)).toEqual([]));
  expect(screen.queryByText("Hazırlanıyor…")).toBeNull();
  expect(screen.queryByRole("button", { name: "Yeni görev sohbet seçenekleri" })).toBeNull();
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
  fireEvent.click(screen.getByRole("button", { name: "Yeni görev sohbet seçenekleri" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Sil" }));
  fireEvent.click(screen.getByRole("button", { name: "Kalıcı olarak sil" }));
  await screen.findByRole("button", { name: "Desktop içinde yeni sohbet başlat" });
  // "Görsel ve video üretimi" artık en soldaki rayda yok; ekran komut paletinden açılır.
  expect(screen.queryByRole("button", { name: "Görsel ve video üretimi" })).toBeNull();
  fireEvent.keyDown(window, { key: "k", code: "KeyK", ctrlKey: true });
  const palet = await screen.findByRole("combobox", { name: /Komut, sohbet/ });
  fireEvent.change(palet, { target: { value: "Görsel oluştur" } });
  fireEvent.keyDown(palet, { key: "Enter" });
  // Basit mod varsayılandır; iş akışı seçildiğinde düğümlü tuval açılır.
  expect(await screen.findByRole("heading", { name: "Görsel oluştur" })).toBeTruthy();
  expect(screen.getByLabelText("Nasıl bir görsel istiyorsun?")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "İş akışı" }));
  expect(screen.getByLabelText("Metin istemi")).toBeTruthy();
  expect(screen.getByRole("region", { name: "Görsel iş akışı tuvali" })).toBeTruthy();
  expect(screen.queryByRole("tab", { name: "Video" })).toBeNull();
  expect(screen.queryByRole("heading", { name: "Yakında" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Saklı sohbet sohbet seçenekleri" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Sil" }));
  fireEvent.click(screen.getByRole("button", { name: "Kalıcı olarak sil" }));
  await waitFor(() => expect(screen.queryByRole("button", { name: "Saklı sohbet" })).toBeNull());
  expect(fake.requests.some((request) => request.ad === "sohbet.sil" && request.veri.sohbet_id === "sakli")).toBe(true);
});

it("boş shell profil hedefi için yeni çekirdek açıp istenen sayfaya gider", async () => {
  const fake = composerTransport({ "sohbet.sil": { ok: true }, "sohbet.listele": { ok: true, sohbetler: [] } });
  render(<SessionUygulama transport={fake.transport} />);
  fireEvent.click(await screen.findByRole("button", { name: "Yeni görev sohbet seçenekleri" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Sil" }));
  fireEvent.click(screen.getByRole("button", { name: "Kalıcı olarak sil" }));
  await screen.findByRole("button", { name: "Desktop içinde yeni sohbet başlat" });
  fireEvent.click(screen.getByRole("button", { name: "Hesap menüsü" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Ayarlar" }));
  await screen.findByRole("heading", { name: "Ayarlar" });
  expect(vi.mocked(fake.transport.create).mock.calls[1][1]).toBe("/Users/test/Desktop");
});

it("tek istemcili uygulamada da alt ajanlar sağ panelden izlenir", async () => {
 const fake = fakeClient();
 render(<Uygulama istemci={fake.client} />);
 await act(async () => fake.receive(JSON.stringify({ tip: "olay", veri: { olay: "SubAgentStarted", sub_id: "agent-a", title: "Kaynak uzmanı", task: "Kaynakları oku", persona: "yardimci" } })));
 fireEvent.click(screen.getByRole("tab", { name: "Ajanlar" }));
 expect(screen.getByRole("button", { name: /Kaynak uzmanı/ })).toBeTruthy();
});

describe("SessionUygulama — dalga 4 (U3-25, U3-26, U3-27, U3-32)", () => {
  it("mutlak yolla başlayan normal istem komut olarak değil görev olarak gider (U3-25)", async () => {
    const fake = composerTransport({ "gecmis.kaynaklar": { ok: true, kaynaklar: [] } });
    render(<SessionUygulama transport={fake.transport} />);
    const textbox = await screen.findByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "/Users/ben/app.py neden çöküyor?" } });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));
    await waitFor(() => expect(fake.requests.some((request) =>
      request.ad === "tur.calistir" && request.veri.gorev === "/Users/ben/app.py neden çöküyor?")).toBe(true));
    expect(fake.requests.some((request) => request.ad === "komut.calistir")).toBe(false);
  });

  it("yolu çözülemeyen tarayıcı bırakması çıplak dosya adıyla eklenmez (U3-26)", async () => {
    const fake = composerTransport({ "gecmis.kaynaklar": { ok: true, kaynaklar: [] } });
    const { container } = render(<SessionUygulama transport={fake.transport} />);
    await screen.findByRole("textbox", { name: "Mesaj" });
    const dosya = new File(["x"], "gizli.txt");
    fireEvent.drop(container.querySelector(".composer")!, { dataTransfer: { files: [dosya] } });
    expect(await screen.findByText(/geçerli bir dosya yolu bulunamadı/i)).toBeTruthy();
    expect(screen.queryByText("gizli.txt")).toBeNull();
  });

  it("yetenek.katalog reddedilse de yerel ve komut listesi boşalmaz (U3-27)", async () => {
    const fake = composerTransport({
      "gecmis.kaynaklar": { ok: true, kaynaklar: [] },
      "komut.listele": { ok: true, komutlar: [{ ad: "model", aciklama: "Modeli değiştir", grup: "Komut" }] },
    });
    const send = fake.transport.send as ReturnType<typeof vi.fn>;
    const asil = send.getMockImplementation()!;
    send.mockImplementation(async (id: string, line: string) => {
      const istek = JSON.parse(line) as { ad: string; id: string };
      if (istek.ad === "yetenek.katalog") throw new Error("katalog kapalı");
      return asil(id, line);
    });
    render(<SessionUygulama transport={fake.transport} />);
    const textbox = await screen.findByRole("textbox", { name: "Mesaj" });
    fireEvent.change(textbox, { target: { value: "/mod" } });
    expect(await screen.findByRole("option", { name: /model.*Modeli değiştir/i })).toBeTruthy();
  });

  it("klasör komutu için depo okunamasa/yazılamasa bile seçici çalışır ve klasör açılır (U3-32)", async () => {
    const fake = composerTransport({ "gecmis.kaynaklar": { ok: true, kaynaklar: [] } });
    const gercekGet = Storage.prototype.getItem, gercekSet = Storage.prototype.setItem;
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key: string) {
      if (key === "fusion.last-project-root") throw new DOMException("engelli", "SecurityError");
      return gercekGet.call(this, key);
    });
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key: string, value: string) {
      if (key === "fusion.last-project-root") throw new DOMException("dolu", "QuotaExceededError");
      return gercekSet.call(this, key, value);
    });
    try {
      const selectFolder = vi.fn(async () => "/Users/test/proje");
      const permissionBridge: PermissionBridge = { request: vi.fn(async () => "granted"), openSettings: vi.fn() };
      render(<SessionUygulama permissionBridge={permissionBridge} selectFolder={selectFolder} transport={fake.transport} />);
      const alan = await screen.findByRole("textbox", { name: "Mesaj" });
      fireEvent.change(alan, { target: { value: "/klasor" } });
      fireEvent.keyDown(alan, { key: "Enter" });
      fireEvent.keyDown(alan, { key: "Enter" });
      const devam = await screen.findByRole("button", { name: "Devam et" }).catch(() => null);
      if (devam) fireEvent.click(devam);
      await waitFor(() => expect(selectFolder).toHaveBeenCalled());
      await waitFor(() => expect(vi.mocked(fake.transport.create).mock.calls.at(-1)?.[1]).toBe("/Users/test/proje"));
      expect(screen.queryByText(/Klasör açılamadı/)).toBeNull();
    } finally { getItem.mockRestore(); setItem.mockRestore(); }
  });
});

it("asılı kalmış eski klasör seçicisinin geç gelen sonucu yeni seçimi ezmez (U4-20)", async () => {
  localStorage.setItem("fusion.permission-explanations.v1", JSON.stringify({ workspace: true }));
  const fake = composerTransport({ "gecmis.kaynaklar": { ok: true, kaynaklar: [] } });
  let eskiSecici!: (root: string | null) => void;
  const selectFolder = vi.fn()
    .mockImplementationOnce(() => new Promise<string | null>((resolve) => { eskiSecici = resolve; }))
    .mockResolvedValueOnce("/Users/test/yeni");
  const permissionBridge: PermissionBridge = { request: vi.fn(async () => "granted"), openSettings: vi.fn() };
  render(<SessionUygulama permissionBridge={permissionBridge} selectFolder={selectFolder} transport={fake.transport} />);
  const klasorKomutu = async () => {
    const alan = await screen.findByRole("textbox", { name: "Mesaj" });
    fireEvent.change(alan, { target: { value: "/klasor" } });
    fireEvent.keyDown(alan, { key: "Enter" });
    fireEvent.keyDown(alan, { key: "Enter" });
  };
  await klasorKomutu();
  await waitFor(() => expect(selectFolder).toHaveBeenCalledTimes(1));
  await klasorKomutu();
  await waitFor(() => expect(vi.mocked(fake.transport.create).mock.calls.at(-1)?.[1]).toBe("/Users/test/yeni"));
  const olusturma = vi.mocked(fake.transport.create).mock.calls.length;

  await act(async () => { eskiSecici("/Users/test/eski"); });

  expect(vi.mocked(fake.transport.create).mock.calls.length).toBe(olusturma);
  expect(vi.mocked(fake.transport.create).mock.calls.some((cagri) => cagri[1] === "/Users/test/eski")).toBe(false);
});

it("Ayarlar > Kurulumu yeniden aç, atlanmış sihirbazı baştan gösterir (U5-47)", async () => {
  const fake = composerTransport();
  render(<SessionUygulama transport={fake.transport} />);
  await screen.findByRole("heading", { name: "Yeni görev" });
  fireEvent.click(screen.getByRole("button", { name: "Hesap menüsü" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Ayarlar" }));
  await screen.findByRole("heading", { name: "Ayarlar" });
  fireEvent.click(await screen.findByRole("button", { name: "Kurulumu yeniden aç" }));
  expect(await screen.findByRole("heading", { name: "Fusion'a hoş geldiniz" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Şimdilik atla" }));
  await screen.findByRole("heading", { name: "Yeni görev" });
});

it("yanıtın Kit'e gönder düğmesi pencereyi açar ve etkin oturumun kit.* RPC'lerini kullanır (P-063)", async () => {
  localStorage.setItem("fusion.permission-explanations.v1", JSON.stringify({ workspace: true }));
  const fake = composerTransport({
    "ayar.arayuz": { ok: true, degerler: {} },
    "tur.calistir": { ok: true, metin: "Rapor hazır." },
    "kit.listele": { ok: true, kitler: [{ id: "kod", name: "Kod", fusionAllowed: true }] },
    "kit.durum": { ok: true, kayitlar: [] },
    "kit.gonder": { ok: true, kitId: "kod", taskId: "t1", threadId: "th", status: "queued" },
  });
  render(<SessionUygulama transport={fake.transport} />);
  fireEvent.change(await screen.findByRole("textbox", { name: "Mesaj" }), { target: { value: "Raporu hazırla" } });
  fireEvent.click(screen.getByRole("button", { name: "Gönder" }));
  fireEvent.click(await screen.findByRole("button", { name: "Kit'e gönder" }));
  const dialog = await screen.findByRole("dialog", { name: "Kit'e gönder" });
  expect((await within(dialog).findByRole("option", { name: "Kod" })).textContent).toBe("Kod");
  expect((within(dialog).getByLabelText("Gönderilecek metin") as HTMLTextAreaElement).value).toBe("Rapor hazır.");
  await act(async () => fireEvent.click(within(dialog).getByRole("button", { name: "Kit'e gönder" })));
  await waitFor(() => expect(fake.requests.some((request) => request.ad === "kit.gonder"
    && request.veri.kit === "kod" && request.veri.metin === "Rapor hazır.")).toBe(true));
  expect(await within(dialog).findByText(/kuyruğa alındı/)).toBeTruthy();
  fireEvent.click(within(dialog).getByRole("button", { name: "Kapat" }));
  await waitFor(() => expect(screen.queryByRole("dialog", { name: "Kit'e gönder" })).toBeNull());
});


it("etkin sohbetten görsel sayfasına geçer, geri ve ileri gezinir", async () => {
  const fake = composerTransport({});
  render(<SessionUygulama transport={fake.transport} />);
  await screen.findByRole("textbox", { name: "Mesaj" });
  fireEvent.keyDown(window, { key: "k", code: "KeyK", ctrlKey: true });
  const palet = await screen.findByRole("combobox", { name: /Komut, sohbet/ });
  fireEvent.change(palet, { target: { value: "Görsel oluştur" } });
  fireEvent.keyDown(palet, { key: "Enter" });
  expect(await screen.findByRole("heading", { name: "Görsel oluştur" })).toBeTruthy();
  expect(screen.queryByRole("tab", { name: "Video" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Geri git" }));
  expect(await screen.findByRole("textbox", { name: "Mesaj" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "İleri git" }));
  expect(await screen.findByRole("heading", { name: "Görsel oluştur" })).toBeTruthy();
  expect(fake.transport.create).toHaveBeenCalledTimes(1);
});

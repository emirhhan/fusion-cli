import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FeedbackDialog } from "./FeedbackDialog";
import { useCrashReporter } from "./useCrashReporter";

afterEach(cleanup);

const surum = () => Promise.resolve("0.4.6");

describe("FeedbackDialog", () => {
  it("boş mesajla gönderilemez; yazınca GitHub adresi açılır", async () => {
    const open = vi.fn().mockResolvedValue(undefined);
    render(<FeedbackDialog loadVersion={surum} onClose={vi.fn()} openExternal={open} />);

    const gonder = screen.getByRole("button", { name: "GitHub'da aç" });
    expect((gonder as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Karanlık tema çok güzel" } });
    await waitFor(() => expect(screen.getByRole("radio", { name: "Öneri veya görüş" }).getAttribute("aria-checked")).toBe("true"));
    fireEvent.click(gonder);

    await waitFor(() => expect(open).toHaveBeenCalledTimes(1));
    const url = new URL(open.mock.calls[0][0]);
    expect(url.searchParams.get("title")).toBe("[Geri bildirim] Karanlık tema çok güzel");
    expect((await screen.findByRole("status")).textContent).toContain("tarayıcıda açıldı");
  });

  it("hata akışında teknik ayrıntıyı ekler, işaret kaldırılınca çıkarır", async () => {
    const open = vi.fn().mockResolvedValue(undefined);
    render(
      <FeedbackDialog
        initial={{ tur: "hata", mesaj: "Tur çöktü", ayrinti: "TypeError at /Users/ali/app.ts" }}
        loadVersion={surum}
        onClose={vi.fn()}
        openExternal={open}
      />,
    );
    expect(screen.getByRole("heading").textContent).toContain("Hata bildir");
    expect(screen.getByText("TypeError at ~/app.ts")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "GitHub'da aç" }));
    await waitFor(() => expect(open).toHaveBeenCalledTimes(1));
    expect(new URL(open.mock.calls[0][0]).searchParams.get("body")).toContain("TypeError at ~/app.ts");

    fireEvent.click(screen.getByRole("checkbox", { name: "Teknik ayrıntıyı ekle" }));
    fireEvent.click(screen.getByRole("button", { name: "GitHub'da aç" }));
    await waitFor(() => expect(open).toHaveBeenCalledTimes(2));
    expect(new URL(open.mock.calls[1][0]).searchParams.get("body")).not.toContain("TypeError");
  });

  it("tarayıcı açılamazsa kullanıcıya söyler; Escape kapatır", async () => {
    const onClose = vi.fn();
    render(<FeedbackDialog initial={{ mesaj: "x" }} loadVersion={surum} onClose={onClose} openExternal={() => Promise.reject(new Error("yok"))} />);
    fireEvent.click(screen.getByRole("button", { name: "GitHub'da aç" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Tarayıcı açılamadı");
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
  it("modal odak tuzağı kurar: arka plan inert olur, Escape kapatır, kapanınca geri döner (U6-22)", () => {
    // Ölçüldü (30 Ekim): Escape window'da kendi başına dinleniyordu; odak tuzağı/inert yoktu.
    const arka = document.createElement("button");
    document.body.append(arka);
    const kapat = vi.fn();
    const view = render(<FeedbackDialog onClose={kapat} loadVersion={async () => "1.0"} />);
    expect(arka.inert).toBe(true);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(kapat).toHaveBeenCalledTimes(1);
    view.unmount();
    expect(arka.inert).toBeFalsy();
    arka.remove();
  });

});

describe("useCrashReporter", () => {
  it("yakalanmamış hatayı tutar, zararsız gürültüyü yok sayar ve temizlenir", () => {
    const { result } = renderHook(() => useCrashReporter());
    act(() => { window.dispatchEvent(new ErrorEvent("error", { message: "ResizeObserver loop limit exceeded" })); });
    expect(result.current[0]).toBeNull();

    act(() => { window.dispatchEvent(new ErrorEvent("error", { error: new Error("patladı"), message: "patladı" })); });
    expect(result.current[0]?.mesaj).toBe("patladı");
    expect(result.current[0]?.ayrinti).toContain("patladı");

    act(() => { window.dispatchEvent(new ErrorEvent("error", { error: new Error("ikinci"), message: "ikinci" })); });
    expect(result.current[0]?.mesaj).toBe("patladı");

    act(() => result.current[1]());
    expect(result.current[0]).toBeNull();
  });

  it("iptal edilen istek (AbortError) kullanıcıya hata olarak gösterilmez (U6-23)", () => {
    // Ölçüldü (30 Ekim): yalnız ResizeObserver süzülüyordu; kapanışta iptal edilen fetch yanlış alarm veriyordu.
    const { result } = renderHook(() => useCrashReporter());
    act(() => { window.dispatchEvent(new ErrorEvent("error", { error: new DOMException("The user aborted a request.", "AbortError"), message: "x" })); });
    expect(result.current[0]).toBeNull();
    act(() => { window.dispatchEvent(new ErrorEvent("error", { error: new Error("gerçek hata"), message: "gerçek hata" })); });
    expect(result.current[0]?.mesaj).toBe("gerçek hata");
  });
});

it('çevrimdışı rapor dosyası önizlemeyle aynı temizlenmiş metni içerir', async () => {
  const download = vi.fn();
  render(<FeedbackDialog initial={{ tur: 'hata', mesaj: 'Hata', ayrinti: 'password=SENTINEL_EXPORT' }} loadVersion={surum} onClose={vi.fn()} downloadReport={download} />);
  await screen.findByText(/0.4.6/);
  fireEvent.click(screen.getByRole('button', { name: 'Rapor dosyasını indir' }));
  expect(download).toHaveBeenCalledTimes(1);
  const bundle = JSON.parse(download.mock.calls[0][0]);
  expect(bundle.schemaVersion).toBe(1);
  expect(bundle.report).not.toContain('SENTINEL_EXPORT');
  expect(bundle.manifest.notCollected).toContain('credentials');
  expect(screen.getByLabelText('Rapor önizlemesi').textContent).toBe(bundle.report);

});

describe("FeedbackDialog — tam sayfa (profil menüsü)", () => {
  it("pencere değil sayfa çizer; Kapat önceki ekrana döndürür, Escape sayfayı kapatmaz", () => {
    const onClose = vi.fn();
    render(<FeedbackDialog initial={{ tur: "geri-bildirim" }} loadVersion={async () => "1.0"} onClose={onClose} variant="page" />);

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("main")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Geri bildirim gönder" })).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Kapat" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

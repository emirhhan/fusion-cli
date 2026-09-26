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
});

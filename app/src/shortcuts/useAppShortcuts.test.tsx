import { act, cleanup, render, renderHook, waitFor } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KEYMAP_CACHE_KEY, KEYMAP_CHANGED_EVENT, SHORTCUT_CAPTURE_ATTRIBUTE, useGlobalShortcuts, useKeymap } from "./useAppShortcuts";

afterEach(cleanup);

function Harness({ handler, mac }: { handler: (action: string) => boolean; mac: boolean }) {
  const ref = useRef(handler);
  ref.current = handler;
  useGlobalShortcuts({ "mod+k": "palet", "mod+j": "terminal", "mod+shift+b": "onizleme" }, ref, mac);
  return (
    <div>
      <input aria-label="yaz" />
      <button {...{ [SHORTCUT_CAPTURE_ATTRIBUTE]: "" }} type="button">kayıt</button>
      <div className="xterm"><textarea aria-label="kabuk" ref={swallowLikeXterm} /></div>
    </div>
  );
}

/** xterm işlediği tuşu (Ctrl+harf) iptal eder ve yayılımını durdurur; window dinleyicisi görmez. */
function swallowLikeXterm(node: HTMLTextAreaElement | null) {
  node?.addEventListener("keydown", (event) => { if (event.ctrlKey) { event.preventDefault(); event.stopPropagation(); } });
}

const keydown = (target: EventTarget, init: KeyboardEventInit) => {
  const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init });
  target.dispatchEvent(event);
  return event;
};

describe("global kısayol dinleyicisi", () => {
  it("bağlı tuşta eylemi çalıştırır ve tarayıcı davranışını engeller (yazarken de)", () => {
    const handler = vi.fn(() => true);
    const view = render(<Harness handler={handler} mac={false} />);
    const event = keydown(view.getByLabelText("yaz"), { key: "k", code: "KeyK", ctrlKey: true });
    expect(handler).toHaveBeenCalledWith("palet");
    expect(event.defaultPrevented).toBe(true);
  });

  it("terminalin işaretlediği olayı, tuş kaydını ve bağsız tuşu atlar", () => {
    const handler = vi.fn(() => true);
    const view = render(<Harness handler={handler} mac />);
    const input = view.getByLabelText("yaz");
    input.addEventListener("keydown", (event) => event.preventDefault(), { once: true });
    keydown(input, { key: "k", code: "KeyK", metaKey: true });
    keydown(view.getByText("kayıt"), { key: "j", code: "KeyJ", metaKey: true });
    keydown(input, { key: "x", code: "KeyX", metaKey: true });
    expect(handler).not.toHaveBeenCalled();
  });

  it("Windows/Linux'ta terminal odaktayken terminal tuşu ve Ctrl+Shift bağları uygulamaya geçer", () => {
    // Ölçüldü (31 Ekim): xterm Ctrl+J'yi kabuğa gönderip olayı durdurduğu için terminal paneli
    // odaktayken Ctrl+J ile kapatılamıyordu. Ctrl+K (satır sonunu sil) gibi tuşlar kabukta kalır.
    const handler = vi.fn(() => true);
    const view = render(<Harness handler={handler} mac={false} />);
    const shell = view.getByLabelText("kabuk");
    expect(keydown(shell, { key: "j", code: "KeyJ", ctrlKey: true }).defaultPrevented).toBe(true);
    keydown(shell, { key: "B", code: "KeyB", ctrlKey: true, shiftKey: true });
    keydown(shell, { key: "k", code: "KeyK", ctrlKey: true });
    expect(handler.mock.calls).toEqual([["terminal"], ["onizleme"]]);
  });

  it("işleyici eylemi işlemezse olay engellenmez", () => {
    const view = render(<Harness handler={() => false} mac />);
    expect(keydown(view.getByLabelText("yaz"), { key: "j", code: "KeyJ", metaKey: true }).defaultPrevented).toBe(false);
  });
});

describe("tuş tablosu", () => {
  it("çekirdekten okur, odağa dönünce tazeler, ayar olayıyla güncellenir", async () => {
    let terminalKey = "mod+t";
    const client = { request: vi.fn(async () => ({ ok: true, baglar: { [terminalKey]: "terminal" } })) };
    const { result } = renderHook(() => useKeymap(client));
    expect(result.current.baglar["mod+n"]).toBe("yeni_sohbet");
    await waitFor(() => expect(result.current.baglar).toEqual({ "mod+t": "terminal" }));
    terminalKey = "mod+y";
    act(() => { window.dispatchEvent(new Event("focus")); });
    await waitFor(() => expect(result.current.baglar).toEqual({ "mod+y": "terminal" }));
    act(() => { window.dispatchEvent(new CustomEvent(KEYMAP_CHANGED_EVENT, { detail: { ok: true, baglar: { "mod+u": "palet" } } })); });
    expect(result.current.baglar).toEqual({ "mod+u": "palet" });
  });

  it("çekirdek yokken (boş ekran) son okunan tablo geçerlidir", async () => {
    // Ölçüldü (31 Ekim): etkin oturum yokken `useKeymap(null)` varsayılan tabloya düşüyordu; kullanıcı
    // mod+k'yı başka eyleme verdiyse boş ekranda eski bağ çalışıyordu.
    localStorage.clear();
    const client = { request: vi.fn(async () => ({ ok: true, baglar: { "mod+t": "terminal" } })) };
    const first = renderHook(() => useKeymap(client));
    await waitFor(() => expect(first.result.current.baglar).toEqual({ "mod+t": "terminal" }));
    first.unmount();
    const { result } = renderHook(() => useKeymap(null));
    expect(result.current.baglar).toEqual({ "mod+t": "terminal" });
    act(() => { window.dispatchEvent(new CustomEvent(KEYMAP_CHANGED_EVENT, { detail: { ok: true, baglar: { "mod+u": "palet" } } })); });
    expect(renderHook(() => useKeymap(null)).result.current.baglar).toEqual({ "mod+u": "palet" });
    localStorage.setItem(KEYMAP_CACHE_KEY, "{bozuk");
    expect(renderHook(() => useKeymap(null)).result.current.baglar["mod+n"]).toBe("yeni_sohbet");
    localStorage.clear();
  });

  it("eski çekirdek isteği tanımazsa varsayılanlar kalır", async () => {
    const client = { request: vi.fn(async () => ({ ok: false, metin: "Bilinmeyen istek" })) };
    const { result } = renderHook(() => useKeymap(client));
    await waitFor(() => expect(client.request).toHaveBeenCalled());
    expect(result.current.baglar["ctrl+`"]).toBe("terminal");
  });
});

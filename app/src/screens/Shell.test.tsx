import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Shell } from "./Shell";

function setNarrowViewport(narrow: boolean) {
  const listeners = new Set<(event: MediaQueryListEvent) => void>();
  let matches = narrow;
  const query = "(max-width: 1023px)";
  const media = {
    addEventListener: vi.fn((_type: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.add(listener);
    }),
    get matches() {
      return matches;
    },
    media: query,
    onchange: null,
    removeEventListener: vi.fn((_type: string, listener: (event: MediaQueryListEvent) => void) => {
      listeners.delete(listener);
    }),
  };
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue(media));
  return {
    setNarrow(next: boolean) {
      matches = next;
      const event = { matches: next, media: query } as MediaQueryListEvent;
      listeners.forEach((listener) => listener(event));
    },
  };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Shell", () => {
  it("üç ana bölgeyi doğru semantiklerle sunar", () => {
    render(
      <Shell
        content={<p>Konuşma</p>}
        header={<h1>Başlık</h1>}
        inspector={<p>Dosyalar</p>}
        sidebar={<p>Gezinme</p>}
      />,
    );
    expect(screen.getByRole("navigation", { name: "Ana navigasyon" })).toBeTruthy();
    expect(screen.getByRole("main")).toBeTruthy();
    expect(screen.getByRole("complementary", { name: "Denetçi" })).toBeTruthy();
  });

  it("daraltılmış navigasyon durumunu kabuğa işler", () => {
    const { container } = render(
      <Shell content="İçerik" sidebar="Gezinme" sidebarCollapsed />,
    );
    expect(container.querySelector(".app-shell")?.getAttribute("data-sidebar-collapsed")).toBe(
      "true",
    );
  });

  it("açık denetçiyi Escape ve örtü tıklamasıyla kapatır", () => {
    const onInspectorClose = vi.fn();
    render(
      <Shell
        content="İçerik"
        inspector="Denetçi içeriği"
        inspectorOpen
        onInspectorClose={onInspectorClose}
        sidebar="Gezinme"
      />,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onInspectorClose).toHaveBeenCalledTimes(1);
    screen.getByRole("button", { name: "Denetçiyi kapat" }).click();
    expect(onInspectorClose).toHaveBeenCalledTimes(2);
  });

  it("dar görünüm denetçisinde odağı içeri taşır ve kapanınca geri verir", () => {
    setNarrowViewport(true);
    function InspectorHarness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)} type="button">Denetçiyi göster</button>
          <Shell
            content="İçerik"
            inspector={<button type="button">Dosya eylemi</button>}
            inspectorOpen={open}
            onInspectorClose={() => setOpen(false)}
            sidebar="Gezinme"
          />
        </>
      );
    }

    render(<InspectorHarness />);
    const trigger = screen.getByRole("button", { name: "Denetçiyi göster" });
    trigger.focus();
    fireEvent.click(trigger);

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Dosya eylemi" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(document.activeElement).toBe(trigger);
  });

  it("masaüstünde başlangıçta açık denetçi mevcut odağı çalmaz", () => {
    setNarrowViewport(false);
    render(<button type="button">Başlangıç odağı</button>);
    const trigger = screen.getByRole("button", { name: "Başlangıç odağı" });
    trigger.focus();

    render(
      <Shell
        content="İçerik"
        inspector={<button type="button">Dosya eylemi</button>}
        inspectorOpen
        sidebar="Gezinme"
      />,
    );

    expect(document.activeElement).toBe(trigger);
  });

  it("dar başlangıçta varsayılan açık overlay odağı ilk tabbable kontrole alır", () => {
    setNarrowViewport(true);
    render(<button type="button">Dışarıdaki odak</button>);
    const outside = screen.getByRole("button", { name: "Dışarıdaki odak" });
    outside.focus();

    render(
      <Shell
        content="İçerik"
        inspector={
          <>
            <button tabIndex={-1} type="button">Etkin olmayan sekme</button>
            <button tabIndex={0} type="button">Etkin sekme</button>
          </>
        }
        sidebar="Gezinme"
      />,
    );

    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Etkin sekme" }));
  });

  it("masaüstünde açık denetçi compacte geçince odağı overlay içine taşır ve hapseder", () => {
    const viewport = setNarrowViewport(false);
    render(
      <>
        <button type="button">Çalışma alanı eylemi</button>
        <Shell
          content="İçerik"
          inspector={<><button type="button">İlk eylem</button><button type="button">Son eylem</button></>}
          inspectorOpen
          sidebar="Gezinme"
        />
      </>,
    );
    const outside = screen.getByRole("button", { name: "Çalışma alanı eylemi" });
    outside.focus();

    act(() => viewport.setNarrow(true));

    const first = screen.getByRole("button", { name: "İlk eylem" });
    const last = screen.getByRole("button", { name: "Son eylem" });
    expect(document.activeElement).toBe(first);
    last.focus();
    const tab = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Tab" });
    window.dispatchEvent(tab);
    expect(tab.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(first);
  });

  it("odak sahibi overlay kaldırılırsa geçerli önceki odağı geri yükler", () => {
    setNarrowViewport(true);
    const view = render(
      <>
        <button type="button">Önceki eylem</button>
        <Shell content="İçerik" inspector={<button type="button">Overlay eylemi</button>} inspectorOpen={false} sidebar="Gezinme" />
      </>,
    );
    const previous = screen.getByRole("button", { name: "Önceki eylem" });
    previous.focus();
    view.rerender(
      <>
        <button type="button">Önceki eylem</button>
        <Shell content="İçerik" inspector={<button type="button">Overlay eylemi</button>} inspectorOpen sidebar="Gezinme" />
      </>,
    );
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Overlay eylemi" }));

    view.rerender(<button type="button">Önceki eylem</button>);

    expect(previous.isConnected).toBe(true);
    expect(document.activeElement).toBe(previous);
  });

  it("yalnız compact açık inspector için dialog ve modal semantiği kullanır", () => {
    const viewport = setNarrowViewport(false);
    render(<Shell content="İçerik" inspector="Denetçi" inspectorOpen sidebar="Gezinme" />);
    const desktopInspector = screen.getByRole("complementary", { name: "Denetçi" });
    expect(desktopInspector.getAttribute("aria-modal")).toBeNull();

    act(() => viewport.setNarrow(true));

    const dialog = screen.getByRole("dialog", { name: "Denetçi" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(screen.queryByRole("complementary", { name: "Denetçi" })).toBeNull();
  });

  it("masaüstünde sonradan açılan sabit denetçi odağı yerinde bırakır", () => {
    setNarrowViewport(false);
    function DesktopHarness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)} type="button">Denetçiyi göster</button>
          <Shell
            content="İçerik"
            inspector={<button type="button">Dosya eylemi</button>}
            inspectorOpen={open}
            sidebar="Gezinme"
          />
        </>
      );
    }

    render(<DesktopHarness />);
    const trigger = screen.getByRole("button", { name: "Denetçiyi göster" });
    trigger.focus();
    fireEvent.click(trigger);
    expect(document.activeElement).toBe(trigger);
  });

  it("dar overlay içinde Tab odağını son kontrolden ilk kontrole döndürür", () => {
    setNarrowViewport(true);
    function TrapHarness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)} type="button">Denetçiyi göster</button>
          <Shell
            content="İçerik"
            inspector={<><button type="button">İlk eylem</button><button type="button">Son eylem</button></>}
            inspectorOpen={open}
            onInspectorClose={() => setOpen(false)}
            sidebar="Gezinme"
          />
        </>
      );
    }

    render(<TrapHarness />);
    fireEvent.click(screen.getByRole("button", { name: "Denetçiyi göster" }));
    const first = screen.getByRole("button", { name: "İlk eylem" });
    const last = screen.getByRole("button", { name: "Son eylem" });
    last.focus();
    const tab = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Tab" });
    window.dispatchEvent(tab);
    expect(tab.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(first);
  });

  it("roving tablistte tabindex -1 sekmeleri atlayarak odağı iki yönde içeride tutar", () => {
    setNarrowViewport(true);
    function RovingTabsHarness() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)} type="button">Denetçiyi göster</button>
          <Shell
            content="İçerik"
            inspector={
              <>
                <div aria-label="Denetçi araçları" role="tablist">
                  <button aria-selected="false" role="tab" tabIndex={-1} type="button">Dosyalar</button>
                  <button aria-selected="true" role="tab" tabIndex={0} type="button">Değişiklikler</button>
                  <button aria-selected="false" role="tab" tabIndex={-1} type="button">Terminal</button>
                </div>
                <button type="button">Panel eylemi</button>
              </>
            }
            inspectorOpen={open}
            sidebar="Gezinme"
          />
        </>
      );
    }

    render(<RovingTabsHarness />);
    fireEvent.click(screen.getByRole("button", { name: "Denetçiyi göster" }));
    const activeTab = screen.getByRole("tab", { name: "Değişiklikler" });
    const panelAction = screen.getByRole("button", { name: "Panel eylemi" });
    expect(document.activeElement).toBe(activeTab);

    panelAction.focus();
    const tab = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, key: "Tab" });
    window.dispatchEvent(tab);
    expect(tab.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(activeTab);

    const shiftTab = new KeyboardEvent("keydown", {
      bubbles: true,
      cancelable: true,
      key: "Tab",
      shiftKey: true,
    });
    window.dispatchEvent(shiftTab);
    expect(shiftTab.defaultPrevented).toBe(true);
    expect(document.activeElement).toBe(panelAction);
  });

  it("tabbable çocuğu olmayan compact dialog Tab yönlerinde odağı üzerinde tutar", () => {
    setNarrowViewport(true);
    render(<Shell content="İçerik" inspector={<p>Salt okunur denetçi</p>} sidebar="Gezinme" />);
    const dialog = screen.getByRole("dialog", { name: "Denetçi" });
    expect(document.activeElement).toBe(dialog);

    for (const shiftKey of [false, true]) {
      const tab = new KeyboardEvent("keydown", {
        bubbles: true,
        cancelable: true,
        key: "Tab",
        shiftKey,
      });
      window.dispatchEvent(tab);
      expect(tab.defaultPrevented).toBe(true);
      expect(document.activeElement).toBe(dialog);
    }
  });

  it("odaklı çocuk kaldırılınca sıradaki tabbable kontrole ve sonra dialoga yeniden odaklanır", async () => {
    setNarrowViewport(true);
    const view = render(
      <Shell
        content="İçerik"
        inspector={<><button key="temporary" type="button">Geçici eylem</button><button key="persistent" type="button">Kalıcı eylem</button></>}
        sidebar="Gezinme"
      />,
    );
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Geçici eylem" }));

    view.rerender(
      <Shell content="İçerik" inspector={<button key="persistent" type="button">Kalıcı eylem</button>} sidebar="Gezinme" />,
    );
    await waitFor(() => {
      expect(document.activeElement).toBe(screen.getByRole("button", { name: "Kalıcı eylem" }));
    });

    view.rerender(<Shell content="İçerik" inspector={<p>Kontrol kalmadı</p>} sidebar="Gezinme" />);
    await waitFor(() => {
      expect(document.activeElement).toBe(screen.getByRole("dialog", { name: "Denetçi" }));
    });
  });
});

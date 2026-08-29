import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Shell } from "./Shell";

afterEach(cleanup);

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
});

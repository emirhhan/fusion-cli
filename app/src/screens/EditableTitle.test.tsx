import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppHeader } from "./AppHeader";

afterEach(cleanup);

function baslik(onRename?: (name: string) => Promise<void>) {
  return render(
    <AppHeader
      inspectorOpen={false}
      onRename={onRename}
      onToggleInspector={vi.fn()}
      onToggleSidebar={vi.fn()}
      sidebarCollapsed={false}
      title="Eski ad"
    />,
  );
}

describe("başlıktan sohbeti yeniden adlandırma (#443)", () => {
  it("başlığa tıklayınca alan açılır; Enter yeni adı kaydeder", async () => {
    const onRename = vi.fn().mockResolvedValue(undefined);
    baslik(onRename);
    fireEvent.click(screen.getByRole("button", { name: "Sohbeti yeniden adlandır: Eski ad" }));
    const alan = screen.getByRole("textbox", { name: "Sohbet adı" }) as HTMLInputElement;
    expect(alan.value).toBe("Eski ad");
    fireEvent.change(alan, { target: { value: "  Yeni ad  " } });
    await act(async () => { fireEvent.keyDown(alan, { key: "Enter" }); });
    expect(onRename).toHaveBeenCalledWith("Yeni ad");
    expect(screen.queryByRole("textbox", { name: "Sohbet adı" })).toBeNull();
  });

  it("Escape vazgeçer; boş ya da aynı ad kaydedilmez", async () => {
    const onRename = vi.fn().mockResolvedValue(undefined);
    baslik(onRename);
    fireEvent.click(screen.getByRole("button", { name: /Sohbeti yeniden adlandır/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Sohbet adı" }), { target: { value: "X" } });
    fireEvent.keyDown(screen.getByRole("textbox", { name: "Sohbet adı" }), { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: /Sohbeti yeniden adlandır/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Sohbet adı" }), { target: { value: "   " } });
    await act(async () => { fireEvent.keyDown(screen.getByRole("textbox", { name: "Sohbet adı" }), { key: "Enter" }); });
    expect(onRename).not.toHaveBeenCalled();
  });

  it("kayıt hatası alanı açık tutar ve hatayı gösterir", async () => {
    const onRename = vi.fn().mockRejectedValue(new Error("Ad kaydedilemedi."));
    baslik(onRename);
    fireEvent.click(screen.getByRole("button", { name: /Sohbeti yeniden adlandır/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Sohbet adı" }), { target: { value: "Yeni" } });
    await act(async () => { fireEvent.keyDown(screen.getByRole("textbox", { name: "Sohbet adı" }), { key: "Enter" }); });
    expect(screen.getByRole("alert").textContent).toBe("Ad kaydedilemedi.");
    expect(screen.getByRole("textbox", { name: "Sohbet adı" })).toBeTruthy();
  });

  it("adlandırma bağlanmadıysa başlık düz metindir", () => {
    baslik();
    expect(screen.getByRole("heading", { name: "Eski ad" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Sohbeti yeniden adlandır/ })).toBeNull();
  });
});

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PermissionPrompt } from "./PermissionPrompt";

afterEach(cleanup);

describe("PermissionPrompt", () => {
  it("ilk kullanımda Türkçe açıklamayı erişilebilir bir iletişim kutusunda gösterir", () => {
    render(
      <PermissionPrompt kind="microphone" phase="preflight" onContinue={vi.fn()} onOpenSettings={vi.fn()} onRetry={vi.fn()} />,
    );

    expect(screen.getByRole("dialog", { name: /mikrofon erişimi/i })).toBeTruthy();
    expect(screen.getByText(/konuşmanızı dinleyebilmesi/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Devam et" })).toBeTruthy();
  });

  it("ret durumunda yeniden deneme ve Sistem Ayarları eylemlerini sunar", () => {
    const onRetry = vi.fn();
    const onOpenSettings = vi.fn();
    const onContinueToNext = vi.fn();
    render(
      <PermissionPrompt kind="speech" phase="denied" onContinue={vi.fn()} onContinueToNext={onContinueToNext} onOpenSettings={onOpenSettings} onRetry={onRetry} />,
    );

    expect(screen.getByText(/konuşma tanıma erişimi izni verilmedi/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));
    fireEvent.click(screen.getByRole("button", { name: "Sistem Ayarlarını Aç" }));
    fireEvent.click(screen.getByRole("button", { name: "Sonraki izne geç" }));

    expect(onRetry).toHaveBeenCalledOnce();
    expect(onOpenSettings).toHaveBeenCalledOnce();
    expect(onContinueToNext).toHaveBeenCalledOnce();
  });

  it("Tab odağını eylemlerinde döndürür ve kapanınca önceki odağı geri verir", () => {
    const priorFocus = document.createElement("button");
    document.body.append(priorFocus);
    priorFocus.focus();

    const { unmount } = render(
      <PermissionPrompt kind="workspace" phase="denied" onContinue={vi.fn()} onOpenSettings={vi.fn()} onRetry={vi.fn()} />,
    );
    const retry = screen.getByRole("button", { name: "Yeniden dene" });
    const settings = screen.getByRole("button", { name: "Sistem Ayarlarını Aç" });

    retry.focus();
    fireEvent.keyDown(retry, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(settings);
    fireEvent.keyDown(settings, { key: "Tab" });
    expect(document.activeElement).toBe(retry);

    unmount();
    expect(document.activeElement).toBe(priorFocus);
    priorFocus.remove();
  });
});

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
    render(
      <PermissionPrompt kind="speech" phase="denied" onContinue={vi.fn()} onOpenSettings={onOpenSettings} onRetry={onRetry} />,
    );

    expect(screen.getByText(/konuşma tanıma erişimi izni verilmedi/i)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));
    fireEvent.click(screen.getByRole("button", { name: "Sistem Ayarlarını Aç" }));

    expect(onRetry).toHaveBeenCalledOnce();
    expect(onOpenSettings).toHaveBeenCalledOnce();
  });
});

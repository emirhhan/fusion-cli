import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { EmptyState } from "./EmptyState";

afterEach(cleanup);

describe("EmptyState", () => {
  it("boş ekranda Fusion karakterini çizer; harf işareti kullanmaz", () => {
    const { container } = render(<EmptyState />);
    // Eskiden pixel "F" logosu duruyordu; kullanıcı karakterin kendisini istedi.
    expect(container.querySelector(".fusion-avatar")).toBeTruthy();
    expect(container.querySelector(".fusion-pixel")).toBeNull();
  });

  it("durum karakterin ifadesine yansır", () => {
    const { container } = render(<EmptyState durum="thinking" />);
    expect(container.querySelector(".fusion-avatar")?.getAttribute("data-state")).toBe("thinking");
  });

  it("önerileri gösterir", () => {
    const onSelectPrompt = vi.fn();
    render(<EmptyState onSelectPrompt={onSelectPrompt} />);
    const prompts = screen.getAllByRole("button");
    expect(prompts).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "Yeni bir web projesi oluştur" }));
    expect(onSelectPrompt).toHaveBeenCalledWith("Yeni bir web projesi oluştur");
  });

  it("yüksek çözünürlüklü karakteri kırpmayan kapsayıcıda gösterir", () => {
    render(<EmptyState />);
    expect(
      screen.getByRole("img", { name: "Fusion bekliyor" }).parentElement?.parentElement?.classList
        .contains("empty-state__character--uncropped"),
    ).toBe(true);
  });
});

it("boş sohbet başlığı seçilen projeyle güncellenir", () => {
  const view = render(<EmptyState projectName="Desktop" />);
  expect(screen.getByRole("heading", { name: "Desktop içinde ne üzerinde çalışıyoruz?" })).toBeTruthy();
  view.rerender(<EmptyState projectName="Oyun" />);
  expect(screen.getByRole("heading", { name: "Oyun içinde ne üzerinde çalışıyoruz?" })).toBeTruthy();
  expect(screen.queryByRole("heading", { name: /Desktop/ })).toBeNull();
});

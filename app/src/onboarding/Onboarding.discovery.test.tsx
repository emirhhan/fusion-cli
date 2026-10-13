import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Onboarding, type OnboardingProps } from "./Onboarding";

afterEach(cleanup);

function draw(overrides: Partial<OnboardingProps> = {}) {
  const props: OnboardingProps = {
    apprentice: { active: true, recommendedModel: null },
    onChange: vi.fn(), onComplete: vi.fn(), onResetToApprentice: vi.fn(), onSkip: vi.fn(),
    projects: [], providers: [], runtime: { status: "ready" }, sources: [],
    value: { step: "sources", selectedProjectId: null }, ...overrides,
  };
  render(<Onboarding {...props} />);
  return props;
}

describe("Karşılama — doğru keşif ve projesiz devam", () => {
  it("sayısı bildirilmemiş bulunan kaynağa sıfır öğe uydurmaz", () => {
    draw({ sources: [{ kind: "codex", status: "found" }] });
    expect(screen.queryByText("0 öğe")).toBeNull();
    expect(screen.getByText("Bulundu")).toBeTruthy();
  });
  it("boş keşifte bulunan kaynak başlığı kullanmaz", () => {
    draw();
    expect(screen.queryByRole("heading", { name: "Kaynaklarınız bulundu" })).toBeNull();
    expect(screen.getByRole("heading", { name: /kaynak.*bulunamadı/i })).toBeTruthy();
  });
  it("proje seçmeden açık tamamlamayı ayrı eylemle sunar", () => {
    const props = draw({ value: { step: "project", selectedProjectId: null } });
    fireEvent.click(screen.getByRole("button", { name: "Proje seçmeden devam et" }));
    expect(props.onComplete).toHaveBeenCalledWith({ selectedProjectId: null });
    expect(props.onSkip).not.toHaveBeenCalled();
  });
});

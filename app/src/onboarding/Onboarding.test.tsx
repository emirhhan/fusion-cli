import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Onboarding, type OnboardingProps } from "./Onboarding";
import type { OnboardingValue } from "./types";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const runtime = { status: "ready" as const, version: "0.3.0" };

const sources = [
  { kind: "claude" as const, status: "found" as const, itemCount: 12 },
  { kind: "codex" as const, status: "found" as const, itemCount: 4 },
  { kind: "hermes" as const, status: "not-found" as const },
];

const providers = [
  { id: "openai", name: "OpenAI", secretConfigured: true, status: "ready" as const },
  { id: "anthropic", name: "Anthropic", secretConfigured: false, status: "needs-setup" as const },
  { id: "local", name: "Yerel model", secretConfigured: false, status: "unavailable" as const },
];

const projects = [
  { id: "starter", name: "Fusion başlangıç projesi", description: "Hazır örnek çalışma alanı" },
  { id: "blank", name: "Boş proje", description: "Temiz bir klasörle başlayın" },
];

function renderAt(step: OnboardingValue["step"], overrides: Partial<OnboardingProps> = {}) {
  const props: OnboardingProps = {
    onChange: vi.fn(),
    onComplete: vi.fn(),
    onSkip: vi.fn(),
    projects,
    providers,
    runtime,
    sources,
    value: { step, selectedProjectId: null },
    ...overrides,
  };
  render(<Onboarding {...props} />);
  return props;
}

function ControlledOnboarding({ onSkip = vi.fn() }: { onSkip?: (value: OnboardingValue) => void }) {
  const [value, setValue] = useState<OnboardingValue>({
    step: "welcome",
    selectedProjectId: null,
  });

  return (
    <Onboarding
      onChange={setValue}
      onComplete={vi.fn()}
      onSkip={onSkip}
      projects={[]}
      providers={[]}
      runtime={runtime}
      sources={[]}
      value={value}
    />
  );
}

describe("Onboarding", () => {
  it("kontrollü değer üzerinden ileri ve geri gider", () => {
    render(<ControlledOnboarding />);

    expect(screen.getByRole("heading", { name: "Fusion'a hoş geldiniz" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "İleri" }));
    expect(screen.getByRole("heading", { name: "Çalışma zamanı hazır" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Geri" }));
    expect(screen.getByRole("heading", { name: "Fusion'a hoş geldiniz" })).toBeTruthy();
  });

  it("atlamayı mevcut kontrollü değerle dışarı bildirir", () => {
    const onSkip = vi.fn();
    render(<ControlledOnboarding onSkip={onSkip} />);

    fireEvent.click(screen.getByRole("button", { name: "Şimdilik atla" }));

    expect(onSkip).toHaveBeenCalledWith({ step: "welcome", selectedProjectId: null });
  });

  it("runtime sürümünü ve hazır durumunu gösterir", () => {
    renderAt("runtime");

    expect(screen.getByText("Sürüm 0.3.0")).toBeTruthy();
    expect(screen.getByText("Fusion yerel çalışma zamanı kullanıma hazır.")).toBeTruthy();
  });

  it("bulunan Claude, Codex ve Hermes kaynaklarını metinsel durumlarıyla listeler", () => {
    renderAt("sources");

    expect(screen.getByRole("heading", { name: "Kaynaklarınız bulundu" })).toBeTruthy();
    expect(screen.getByText("Claude")).toBeTruthy();
    expect(screen.getByText("12 öğe")).toBeTruthy();
    expect(screen.getByText("Codex")).toBeTruthy();
    expect(screen.getByText("4 öğe")).toBeTruthy();
    expect(screen.getByText("Hermes")).toBeTruthy();
    expect(screen.getByText("Bulunamadı")).toBeTruthy();
  });

  it("sağlayıcıların güvenli özet durumlarını gösterir", () => {
    renderAt("providers");

    expect(screen.getByRole("heading", { name: "Sağlayıcı durumu" })).toBeTruthy();
    expect(screen.getByText("OpenAI")).toBeTruthy();
    expect(screen.getByText("Hazır")).toBeTruthy();
    expect(screen.getByText("Kurulum gerekli")).toBeTruthy();
    expect(screen.getByText("Kullanılamıyor")).toBeTruthy();
  });

  it("örnek proje seçimini kontrollü değer olarak dışarı bildirir", () => {
    const { onChange } = renderAt("project");

    fireEvent.click(screen.getByRole("button", { name: /Fusion başlangıç projesi/ }));

    expect(onChange).toHaveBeenCalledWith({ step: "project", selectedProjectId: "starter" });
  });

  it("son adımda seçili projeyle tamamlanır", () => {
    const onComplete = vi.fn();
    renderAt("complete", {
      onComplete,
      value: { step: "complete", selectedProjectId: "starter" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Fusion'ı aç" }));

    expect(onComplete).toHaveBeenCalledWith({ selectedProjectId: "starter" });
  });

  it("adım değişince başlığı odaklar ve etkin adımı semantik olarak işaretler", () => {
    render(<ControlledOnboarding />);

    fireEvent.click(screen.getByRole("button", { name: "İleri" }));

    const heading = screen.getByRole("heading", { name: "Çalışma zamanı hazır" });
    expect(document.activeElement).toBe(heading);
    expect(screen.getByText("Çalışma zamanı").closest("li")?.getAttribute("aria-current")).toBe("step");
  });

  it("Alt ve ok tuşlarıyla ileri geri gezinir", () => {
    render(<ControlledOnboarding />);

    fireEvent.keyDown(window, { altKey: true, key: "ArrowRight" });
    expect(screen.getByRole("heading", { name: "Çalışma zamanı hazır" })).toBeTruthy();

    fireEvent.keyDown(window, { altKey: true, key: "ArrowLeft" });
    expect(screen.getByRole("heading", { name: "Fusion'a hoş geldiniz" })).toBeTruthy();
  });

  it("anahtar biçimli dış değeri gizler ve localStorage'a yazmaz", () => {
    const secret = "sk-test-1234567890abcdefghijkl";
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const unsafeProvider = {
      id: "unsafe",
      name: `OpenAI ${secret}`,
      secretConfigured: true,
      status: "ready" as const,
      apiKey: secret,
    };

    const { container } = render(
      <Onboarding
        onChange={vi.fn()}
        onComplete={vi.fn()}
        onSkip={vi.fn()}
        projects={projects}
        providers={[unsafeProvider]}
        runtime={runtime}
        sources={sources}
        value={{ step: "providers", selectedProjectId: null }}
      />,
    );

    expect(container.textContent).not.toContain(secret);
    expect(container.textContent).toContain("[gizlendi]");
    expect(setItem).not.toHaveBeenCalled();
  });
});

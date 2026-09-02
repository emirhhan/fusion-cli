import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TierBar } from "./TierBar";

afterEach(cleanup);

const tiers = [
  { ad: "low", etiket: "Nemotron 3 Super 120B — en hızlısı", model: "nvidia_nim/a" },
  { ad: "medium", etiket: "GPT-OSS 120B — akıl yürütmeye ayarlı", model: "nvidia_nim/b" },
  { ad: "high", etiket: "DeepSeek V4 Flash — kodlamada güçlü", model: "nvidia_nim/c" },
];

describe("TierBar", () => {
  it("etkin kademeyi gösterir ve seçimi bildirir", () => {
    const onSelect = vi.fn();
    render(<TierBar active="medium" editable onSelect={onSelect} tiers={tiers} />);

    expect(screen.getByText("medium")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /high/ }));
    expect(onSelect).toHaveBeenCalledWith("high");
  });

  it("ok tuşlarıyla kademe değiştirir", () => {
    const onSelect = vi.fn();
    render(<TierBar active="medium" editable onSelect={onSelect} tiers={tiers} />);

    fireEvent.keyDown(screen.getByRole("slider"), { key: "ArrowRight" });
    expect(onSelect).toHaveBeenCalledWith("high");
  });

  it("uçta ok tuşu seçimi taşırmaz", () => {
    const onSelect = vi.fn();
    render(<TierBar active="low" editable onSelect={onSelect} tiers={tiers} />);

    fireEvent.keyDown(screen.getByRole("slider"), { key: "ArrowLeft" });
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("kilitliyken seçim yapılamaz ve gerekçe gösterilir", () => {
    const onSelect = vi.fn();
    render(
      <TierBar
        active="medium"
        editable={false}
        onSelect={onSelect}
        reason="NVIDIA sağlayıcısıyla çalışır."
        tiers={tiers}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /high/ }));
    expect(onSelect).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByRole("slider"), { key: "ArrowRight" });
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByTitle("NVIDIA sağlayıcısıyla çalışır.")).toBeTruthy();
  });

  it("kademe yoksa hiçbir şey çizmez", () => {
    const { container } = render(<TierBar active="" editable onSelect={vi.fn()} tiers={[]} />);
    expect(container.firstChild).toBeNull();
  });
});

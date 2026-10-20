import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VoiceSettings } from "./VoiceSettings";

afterEach(cleanup);

const PREFS = { hiz: 1 };

describe("VoiceSettings", () => {
  it("hız sürgüsü değeri gösterir, robotik sürgüsü yoktur", () => {
    render(
      <VoiceSettings onChange={vi.fn()} onTop onTopChange={vi.fn()} prefs={{ ...PREFS, hiz: 1.25 }} />,
    );
    expect(screen.getByText("1.25×")).toBeTruthy();
    expect(screen.queryByLabelText("Robotik")).toBeNull();
  });

  it("sürgü BIRAKILINCA gönderilir, sürüklerken değil", () => {
    const onChange = vi.fn();
    render(<VoiceSettings onChange={onChange} onTop onTopChange={vi.fn()} prefs={PREFS} />);
    const hiz = screen.getByLabelText("Hız");

    fireEvent.change(hiz, { target: { value: "1.4" } });
    expect(onChange).not.toHaveBeenCalled();

    fireEvent.mouseUp(hiz);
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ hiz: 1.4 }));
  });

  it("hep üstte kal seçeneğini yansıtır", () => {
    const onTopChange = vi.fn();
    render(<VoiceSettings onChange={vi.fn()} onTop={false} onTopChange={onTopChange} prefs={PREFS} />);
    fireEvent.click(screen.getByLabelText("Hep üstte kal"));
    expect(onTopChange).toHaveBeenCalledWith(true);
  });

  it("ana Ayarlar ekranında pencereye özel hep üstte seçeneğini gizler", () => {
    render(
      <VoiceSettings
        onChange={vi.fn()}
        onTop={false}
        onTopChange={vi.fn()}
        prefs={PREFS}
        showOnTop={false}
      />,
    );

    expect(screen.queryByLabelText("Hep üstte kal")).toBeNull();
  });

  it("kayıt sürerken çakışan tercih değişikliklerini engeller", () => {
    render(<VoiceSettings disabled onChange={vi.fn()} onTop onTopChange={vi.fn()} prefs={PREFS} />);

    expect((screen.getByLabelText("Hız") as HTMLInputElement).disabled).toBe(true);
  });

  it("ses klonlama ya da model seçme vaat eden düğme göstermez", () => {
    render(<VoiceSettings onChange={vi.fn()} onTop onTopChange={vi.fn()} prefs={PREFS} />);
    expect(screen.queryByRole("button", { name: /model|kendi ses/i })).toBeNull();
  });
});

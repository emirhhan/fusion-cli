import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VoiceSettings } from "./VoiceSettings";

afterEach(cleanup);

const PREFS = { hiz: 1, model: null, robotik: 0.5 };

describe("VoiceSettings", () => {
  it("hız ve robotiklik sürgüleri değeri gösterir", () => {
    render(
      <VoiceSettings onChange={vi.fn()} onTop onTopChange={vi.fn()} prefs={{ ...PREFS, hiz: 1.25 }} />,
    );
    expect(screen.getByText("1.25×")).toBeTruthy();
    expect(screen.getByText("50%")).toBeTruthy();
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

  it("kendi ses dosyası seçilince adını gösterir", () => {
    render(
      <VoiceSettings
        onChange={vi.fn()}
        onPickModel={vi.fn()}
        onTop
        onTopChange={vi.fn()}
        prefs={{ ...PREFS, model: "/Users/e/sesler/benim.onnx" }}
      />,
    );
    expect(screen.getByText("benim.onnx")).toBeTruthy();
  });
});

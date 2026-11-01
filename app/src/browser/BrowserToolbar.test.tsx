import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { BrowserToolbar, type BrowserToolbarProps } from "./BrowserToolbar";

afterEach(cleanup);

function props(overrides: Partial<BrowserToolbarProps> = {}): BrowserToolbarProps {
  return {
    address: "", busy: false, isOpen: true, picking: false, consoleOpen: false, viewportId: "masaustu",
    onAddressChange: vi.fn(), onSubmit: vi.fn(), onHistory: vi.fn(), onViewport: vi.fn(),
    onPickToggle: vi.fn(), onScreenshot: vi.fn(), onConsole: vi.fn(), ...overrides,
  };
}

test("Cmd/Ctrl+Shift+S öğe seçiciyi açar; sayfa kapalıyken çalışmaz (#444)", () => {
  const onPickToggle = vi.fn();
  const view = render(<BrowserToolbar {...props({ onPickToggle })} />);
  fireEvent.keyDown(document, { key: "S", code: "KeyS", metaKey: true, shiftKey: true });
  fireEvent.keyDown(document, { key: "s", code: "KeyS", ctrlKey: true, shiftKey: true });
  expect(onPickToggle).toHaveBeenCalledTimes(2);
  fireEvent.keyDown(document, { key: "s", code: "KeyS", metaKey: true });
  expect(onPickToggle).toHaveBeenCalledTimes(2);
  view.rerender(<BrowserToolbar {...props({ onPickToggle, isOpen: false })} />);
  fireEvent.keyDown(document, { key: "S", code: "KeyS", metaKey: true, shiftKey: true });
  expect(onPickToggle).toHaveBeenCalledTimes(2);
});

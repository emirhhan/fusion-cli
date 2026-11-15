import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { EffortMenu } from "./EffortMenu";

afterEach(cleanup);

test("Cmd/Ctrl+Shift+E efor menüsünü açar, seçim /effort düzeyini gönderir (#444)", () => {
  const onSelect = vi.fn();
  render(<EffortMenu onSelect={onSelect} />);
  expect(screen.queryByRole("menu", { name: "Efor" })).toBeNull();
  fireEvent.keyDown(document, { key: "E", code: "KeyE", metaKey: true, shiftKey: true });
  fireEvent.click(screen.getByRole("menuitem", { name: "high" }));
  expect(onSelect).toHaveBeenCalledExactlyOnceWith("high");
  expect(screen.queryByRole("menu", { name: "Efor" })).toBeNull();
  fireEvent.keyDown(document, { key: "e", code: "KeyE", ctrlKey: true, shiftKey: true });
  expect(screen.getByRole("menu", { name: "Efor" })).toBeTruthy();
});

test("devre dışıyken kısayol çalışmaz", () => {
  render(<EffortMenu disabled onSelect={vi.fn()} />);
  fireEvent.keyDown(document, { key: "E", code: "KeyE", metaKey: true, shiftKey: true });
  expect(screen.queryByRole("menu", { name: "Efor" })).toBeNull();
});

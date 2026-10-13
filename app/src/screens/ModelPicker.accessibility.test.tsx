import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ModelPicker } from "./ModelPicker";

afterEach(cleanup);
const models = [{ deger: "first", etiket: "First" }, { deger: "second", etiket: "Second" }];

test("model search owns keyboard selection and focus", () => {
  const select = vi.fn();
  render(<ModelPicker active="first" options={models} onSelect={select} />);
  const trigger = screen.getByRole("button", { name: /Model:/ });
  fireEvent.click(trigger);
  const input = screen.getByRole("combobox", { name: "Model ara" });
  expect(document.activeElement).toBe(input);
  expect(input.getAttribute("aria-controls")).toBe(screen.getByRole("listbox").id);
  fireEvent.keyDown(input, { key: "End" });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(select).toHaveBeenCalledWith("second");
  expect(document.activeElement).toBe(trigger);
});

test("Escape closes model picker and restores trigger", () => {
  render(<ModelPicker active="first" options={models} onSelect={vi.fn()} />);
  const trigger = screen.getByRole("button", { name: /Model:/ });
  fireEvent.click(trigger);
  fireEvent.keyDown(screen.getByRole("combobox", { name: "Model ara" }), { key: "Escape" });
  expect(screen.queryByRole("combobox", { name: "Model ara" })).toBeNull();
  expect(document.activeElement).toBe(trigger);
});

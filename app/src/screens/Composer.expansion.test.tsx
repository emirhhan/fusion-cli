import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Composer } from "./Composer";
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
it("resizes long drafts and resets when the draft shrinks", () => {
  vi.spyOn(HTMLTextAreaElement.prototype, "scrollHeight", "get").mockReturnValue(480);
  const { rerender } = render(<Composer onSend={vi.fn()} value={"line\n".repeat(60)} />);
  expect(screen.getByRole("textbox").style.height).toBe("480px");
  vi.spyOn(HTMLTextAreaElement.prototype, "scrollHeight", "get").mockReturnValue(32);
  rerender(<Composer onSend={vi.fn()} value="short" />);
  expect(screen.getByRole("textbox").style.height).toBe("32px");
  expect(screen.getByRole("button", { name: "Gönder" })).toBeTruthy();
});

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ImageJobPanel } from "./ImageJobPanel";
afterEach(cleanup);
it("mobil ayrıntıları açmak işi yeniden başlatmaz veya iptal etmez", () => {
  const recover = vi.fn();
  render(<ImageJobPanel state={{ ready: true, error: null, jobs: [{ jobId: "stable-job", state: "recoveryRequired", busy: false }] }} onRecover={recover} onRetry={vi.fn()} onEmptyFocus={vi.fn()} />);
  const detail = screen.getByRole("button", { name: "İş ayrıntıları" });
  expect(detail.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(detail);
  expect(detail.getAttribute("aria-expanded")).toBe("true");
  expect(recover).not.toHaveBeenCalled();
  fireEvent.click(detail);
  expect(detail.getAttribute("aria-expanded")).toBe("false");
});
it("bulunamayan iş iki adımlı onayla unutulur; diğer işlerde unut düğmesi yoktur", () => {
  const forget = vi.fn();
  const state = { ready: true, error: null, jobs: [
    { jobId: "ghost", state: "recoveryRequired", busy: false, notFound: true },
    { jobId: "belirsiz", state: "recoveryRequired", busy: false },
  ] };
  render(<ImageJobPanel state={state} onRecover={vi.fn()} onRetry={vi.fn()} onForget={forget} onEmptyFocus={vi.fn()} />);
  expect(screen.getAllByRole("button", { name: "Bu işi unut" })).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "Bu işi unut" }));
  expect(forget).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Evet, unut" }));
  expect(forget).toHaveBeenCalledWith("ghost");
});

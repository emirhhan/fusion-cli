import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AUTO_ARCHIVE_PR_KEY, autoArchivePrEnabled } from "../../screens/usePrAutoArchive";
import { General } from "./General";

afterEach(cleanup);
beforeEach(() => localStorage.clear());

test("Genel ayarında PR'a bağlı otomatik arşiv varsayılan kapalı; işaretlenince açılır (#443)", () => {
  render(<General historyOpen onHistoryChange={vi.fn()} onThemeChange={vi.fn()} themePreference="system" />);
  const box = screen.getByRole("checkbox", { name: "PR birleşince ya da kapanınca sohbeti otomatik arşivle" }) as HTMLInputElement;
  expect(box.checked).toBe(false);
  fireEvent.click(box);
  expect(autoArchivePrEnabled()).toBe(true);
  expect(localStorage.getItem(AUTO_ARCHIVE_PR_KEY)).toBe("true");
  expect(box.checked).toBe(true);
});

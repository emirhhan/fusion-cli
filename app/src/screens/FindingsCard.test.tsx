import {cleanup, fireEvent, render, screen} from "@testing-library/react";
import {afterEach, expect, it, vi} from "vitest";
import {FindingsCard} from "./FindingsCard";

afterEach(cleanup);

it("bulguları dosya:satır, özet ve senaryoyla çizer; dosya açılır", () => {
  const open = vi.fn();
  render(<FindingsCard onOpenFile={open} findings={[{file: "a.py", line: 3, summary: "sıfıra bölme",
    failureScenario: "n=0 → ZeroDivisionError", verdict: "CONFIRMED", category: "correctness"}]} />);
  expect(screen.getByRole("region", {name: "İnceleme bulguları"}).textContent).toContain("1 bulgu");
  expect(screen.getByText("sıfıra bölme")).toBeTruthy();
  expect(screen.getByText("n=0 → ZeroDivisionError")).toBeTruthy();
  expect(screen.getByText("doğrulandı")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", {name: "a.py dosyasını aç"}));
  expect(open).toHaveBeenCalledWith("a.py");
});

it("boş liste bulgu yok der", () => {
  render(<FindingsCard findings={[]} />);
  expect(screen.getByRole("region", {name: "İnceleme bulguları"}).textContent).toContain("Doğrulanan bulgu yok");
});

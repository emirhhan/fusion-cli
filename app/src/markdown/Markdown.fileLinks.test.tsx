import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { Markdown } from "./Markdown";
import { projectFilePath } from "./remoteContentPolicy";

afterEach(cleanup);

describe("project artifact links", () => {
  test.each([
    "", ".", "./", " report.html", "report.html ", "report\n.html", "report\t.html",
    "report\u0000.html", "report\u007f.html", "report\u0085.html", "report%C2%85.html",
    "..\\report.html", "\\\\server\\report.html", "site%2Freport.html", "site%5Creport.html",
    "./C:/report.html", "./../report.html", "site/..%2fsecret.html", "report%253a.html",
  ])("rejects unsafe raw path before any preview dispatch: %j", (path) => {
    expect(projectFilePath(path)).toBeNull();
  });

  test.each([
    ["rapor-guncel-v14.html", "rapor-guncel-v14.html"],
    ["./website-test/index.html", "website-test/index.html"],
    ["sonu%C3%A7%20raporu.html", "sonuç raporu.html"],
  ])("opens %s through the project preview callback", (href, path) => {
    const open = vi.fn();
    const submit = vi.fn();
    const { container } = render(<form onSubmit={submit}><Markdown onOpenFile={open} text={`[**Rapor**](<${href}>)`} /></form>);
    const button = screen.getByRole("button", { name: "Rapor" });
    expect(button.getAttribute("type")).toBe("button");
    expect(button.querySelector("strong")).not.toBeNull();
    expect(open).not.toHaveBeenCalled();
    fireEvent.click(button);
    expect(open).toHaveBeenCalledExactlyOnceWith(path);
    expect(submit).not.toHaveBeenCalled();
    expect(container.querySelector("a")).toBeNull();
  });

  test("has no actionable file control without a preview callback", () => {
    const { container } = render(<Markdown text="[Rapor](rapor.html)" />);
    expect(screen.getByText("Rapor")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
  });

  test("file link labels keep image descriptions passive instead of nesting image controls", () => {
    const open = vi.fn();
    const { container } = render(<Markdown onOpenFile={open} text="[**Rapor** ![Önizleme](https://example.com/thumb.png)](rapor.html)" />);
    const button = container.querySelector<HTMLButtonElement>(".markdown__file-link")!;
    expect(button).not.toBeNull();
    expect(button.querySelector("button")).toBeNull();
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Rapor Önizleme" })).toBe(button);
    expect(button.querySelector("strong")).not.toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(open).not.toHaveBeenCalled();
    fireEvent.click(button);
    expect(open).toHaveBeenCalledExactlyOnceWith("rapor.html");
  });

  test("empty image labels retain the file path as an accessible name", () => {
    const open = vi.fn();
    const { container } = render(<Markdown onOpenFile={open} text="[![](thumb.png)](rapor.html)" />);
    const button = screen.getByRole("button", { name: "rapor.html" });
    expect(screen.getAllByRole("button")).toHaveLength(1);
    expect(container.querySelector("img")).toBeNull();
    expect(open).not.toHaveBeenCalled();
    fireEvent.click(button);
    expect(open).toHaveBeenCalledExactlyOnceWith("rapor.html");
  });

  test.each([
    "../secrets.html", "site/../../secrets.html", "%2e%2e/secrets.html", "site/%2e%2e/secrets.html",
    "site%2findex.html", "site%5cindex.html", "%2fetc/passwd", "%252e%252e/secrets.html",
    "/etc/passwd", "//outside.example/report.html", "C:/secrets.html", "C%3a/secrets.html",
    "file:///etc/passwd", "javascript:alert(1)", "data:text/html,hello", "tauri://localhost",
    "site//index.html", "site/./index.html", "site/..%20/secrets.html", "site./index.html",
    "report.html?download=1", "report.html#section", "report%00.html", "report%0a.html",
    "report%7f.html", "report%85.html", "bad%zz.html",
  ])("keeps unsafe or ambiguous path %s inert", (href) => {
    const open = vi.fn();
    const { container } = render(<Markdown onOpenFile={open} text={`[Rapor](<${href}>)`} />);
    expect(screen.getByText("Rapor")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    fireEvent.click(screen.getByText("Rapor"));
    expect(open).not.toHaveBeenCalled();
  });

  test("preserves external and fragment anchors when file preview is available", () => {
    const open = vi.fn();
    render(<Markdown onOpenFile={open} text="[Kaynak](https://example.com/report) [Eposta](mailto:a@example.com) [Bölüm](#section)" />);
    expect(screen.getByRole("link", { name: "Kaynak" }).getAttribute("href")).toBe("https://example.com/report");
    expect(screen.getByRole("link", { name: "Eposta" }).getAttribute("href")).toBe("mailto:a@example.com");
    expect(screen.getByRole("link", { name: "Bölüm" }).getAttribute("href")).toBe("#section");
    expect(screen.queryByRole("button")).toBeNull();
    expect(open).not.toHaveBeenCalled();
  });
});

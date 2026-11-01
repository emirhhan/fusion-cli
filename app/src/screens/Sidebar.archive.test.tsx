import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";
import { ARCHIVED_SESSIONS_KEY } from "./useArchivedSessions";
import { resetLanguageCache } from "../i18n/language";

const sessions = [
  { session_id: "1", title: "İlk iş", source: "fusion", project: "Desktop" },
  { session_id: "2", title: "İkinci iş", source: "fusion", project: "Desktop" },
];

afterEach(() => cleanup());
beforeEach(() => { localStorage.clear(); resetLanguageCache(); });

describe("Sidebar arşivi (#443)", () => {
  it("menünün ilk eylemi Arşivle; arşivlenen sohbet ana listeden kalkar, Arşivlenenler görünümünde durur", () => {
    render(<Sidebar oturumlar={sessions} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} onSil={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "İkinci iş sohbet seçenekleri" }));
    const items = screen.getAllByRole("menuitem");
    expect(items[0].textContent).toBe("Arşivle");
    expect(items[items.length - 1].textContent).toBe("Sil");
    fireEvent.click(items[0]);

    expect(screen.queryByText("İkinci iş")).toBeNull();
    expect(JSON.parse(localStorage.getItem(ARCHIVED_SESSIONS_KEY) ?? "[]")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Arşivlenenler (1)" }));
    expect(screen.queryByText("İkinci iş")).not.toBeNull();
    expect(screen.queryByText("İlk iş")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "İkinci iş sohbet seçenekleri" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Arşivden çıkar" }));
    fireEvent.click(screen.getByRole("button", { name: "Tüm sohbetler" }));
    expect(screen.queryByText("İkinci iş")).not.toBeNull();
    expect(screen.queryByRole("button", { name: /Arşivlenenler/ })).toBeNull();
  });
});

describe("Sidebar Option-tık (#443)", () => {
  it("Option (Alt) ile tıklanan sohbet yan bölmede açılır; düz tık seçer", () => {
    const onSec = vi.fn();
    const onSplit = vi.fn();
    render(<Sidebar oturumlar={sessions} etkin="1" onSec={onSec} onSplit={onSplit} onYeni={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "İkinci iş" }), { altKey: true });
    expect(onSplit).toHaveBeenCalledWith("2");
    expect(onSec).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "İkinci iş" }));
    expect(onSec).toHaveBeenCalledWith("2");
    // Etkin sohbet kendisinin yanına bölünmez: Option-tık onu yalnız seçer.
    fireEvent.click(screen.getByRole("button", { name: "İlk iş" }), { altKey: true });
    expect(onSplit).toHaveBeenCalledTimes(1);
  });
});

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";
import { ARCHIVED_SESSIONS_KEY } from "./useArchivedSessions";
import { AUTO_ARCHIVE_PR_KEY, AUTO_ARCHIVED_KEY } from "./usePrAutoArchive";
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

describe("Sidebar PR'a bağlı otomatik arşiv (#443)", () => {
  it("ayar açıkken birleşen/kapanan PR'lı sohbet arşivlenir; çalışan sohbet atlanır", async () => {
    localStorage.setItem(AUTO_ARCHIVE_PR_KEY, "true");
    const rows = [...sessions, { session_id: "3", title: "Çalışan iş", source: "fusion", project: "Desktop", calisiyor: true }];
    const prDurumlari = vi.fn(async (ids: string[]) => Object.fromEntries(ids.map((id) => [id, id === "1" ? "OPEN" : "MERGED"])));
    render(<Sidebar oturumlar={rows} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} prDurumlari={prDurumlari} />);
    await waitFor(() => expect(screen.queryByText("İkinci iş")).toBeNull());
    expect(prDurumlari).toHaveBeenCalledWith(["1", "2"]);
    expect(screen.queryByText("İlk iş")).not.toBeNull();
    expect(screen.queryByText("Çalışan iş")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Arşivlenenler (1)" })).toBeTruthy();
  });

  it("ayar kapalıyken sorulmaz; kullanıcının arşivden çıkardığı sohbet yeniden arşivlenmez", async () => {
    const prDurumlari = vi.fn(async () => ({ "2": "CLOSED" }));
    const first = render(<Sidebar oturumlar={sessions} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} prDurumlari={prDurumlari} />);
    expect(prDurumlari).not.toHaveBeenCalled();
    first.unmount();

    localStorage.setItem(AUTO_ARCHIVE_PR_KEY, "true");
    localStorage.setItem(AUTO_ARCHIVED_KEY, JSON.stringify(["fusion:2"]));
    render(<Sidebar oturumlar={sessions} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} prDurumlari={prDurumlari} />);
    await waitFor(() => expect(prDurumlari).toHaveBeenCalled());
    expect(screen.queryByText("İkinci iş")).not.toBeNull();
  });
});

describe("Sidebar Grupla ve sırala (#443)", () => {
  it("gruplama yok seçilince sohbetler tek listede son etkinliğe göre sıralanır; tercih kalır", () => {
    const rows = [
      { session_id: "a", title: "Eski", source: "fusion", project: "A", projectRoot: "/a", updated_at: 1 },
      { session_id: "b", title: "Yeni", source: "fusion", project: "B", projectRoot: "/b", updated_at: 5 },
    ];
    render(<Sidebar oturumlar={rows} etkin={null} onSec={vi.fn()} onYeni={vi.fn()} projeler={[{ root: "/a", name: "A", pinned: false, updated_at: 1 }, { root: "/b", name: "B", pinned: false, updated_at: 5 }]} />);
    expect(screen.queryByRole("region", { name: "Tüm sohbetler" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Grupla ve sırala" }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: "Gruplama yok" }));
    const list = screen.getByRole("region", { name: "Tüm sohbetler" });
    const titles = within(list).getAllByRole("button").map((item) => item.textContent ?? "").filter((text) => text === "Eski" || text === "Yeni");
    expect(titles[0]).toBe("Yeni");
    expect(localStorage.getItem("fusion.sidebar.grouping.v1")).toBe("none");
  });
});

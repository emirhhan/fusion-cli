import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "./Sidebar";

const kayit = { id: "p1", name: "Mağaza", pinned: false, root: "", updated_at: 5 };
const sohbet = { session_id: "c1", source: "fusion", title: "Sepet hatası", project: "Desktop", projectRoot: "/Users/t/Desktop", projectId: "p1" };
const serbest = { session_id: "c2", source: "fusion", title: "Serbest sohbet", project: "Desktop", projectRoot: "/Users/t/Desktop" };

beforeEach(() => localStorage.clear());
afterEach(cleanup);

function kur(extra: Partial<React.ComponentProps<typeof Sidebar>> = {}) {
  const props = {
    etkin: null, onSec: vi.fn(), onYeni: vi.fn(), onNavigate: vi.fn(),
    onProjectCreate: vi.fn(async () => undefined),
    onProjectRename: vi.fn(async () => undefined),
    onProjectDelete: vi.fn(async () => undefined),
    onAssign: vi.fn(async () => undefined),
    oturumlar: [sohbet, serbest], projeler: [kayit],
    ...extra,
  };
  render(<Sidebar {...props} />);
  return props;
}

describe("Sidebar — kalıcı projeler", () => {
  it("Yeni proje ad ister; adı boşken kaydetmez, doluyken oluşturur", async () => {
    const p = kur();
    fireEvent.click(screen.getByRole("button", { name: "Yeni proje" }));
    const kaydet = screen.getByRole("button", { name: "Oluştur" }) as HTMLButtonElement;
    expect(kaydet.disabled).toBe(true);
    fireEvent.change(screen.getByRole("textbox", { name: "Proje adı" }), { target: { value: "  Blog " } });
    fireEvent.click(screen.getByRole("button", { name: "Oluştur" }));
    await waitFor(() => expect(p.onProjectCreate).toHaveBeenCalledWith({ name: "Blog", root: undefined }));
    expect(p.onNavigate).not.toHaveBeenCalledWith("new-project");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("isteğe bağlı klasörü seçtirip projeyle gönderir", async () => {
    const p = kur({ onPickFolder: async () => "/Users/t/blog" });
    fireEvent.click(screen.getByRole("button", { name: "Yeni proje" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Proje adı" }), { target: { value: "Blog" } });
    fireEvent.click(screen.getByRole("button", { name: "Klasör seç" }));
    await screen.findByText("/Users/t/blog");
    fireEvent.click(screen.getByRole("button", { name: "Oluştur" }));
    await waitFor(() => expect(p.onProjectCreate).toHaveBeenCalledWith({ name: "Blog", root: "/Users/t/blog" }));
  });

  it("oluşturma hatasını diyalogda gösterir ve açık bırakır", async () => {
    kur({ onProjectCreate: async () => { throw new Error("Bu adla bir proje zaten var."); } });
    fireEvent.click(screen.getByRole("button", { name: "Yeni proje" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Proje adı" }), { target: { value: "Mağaza" } });
    fireEvent.click(screen.getByRole("button", { name: "Oluştur" }));
    expect((await screen.findByRole("alert")).textContent).toContain("zaten var");
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("proje sohbeti kayıtlı projenin altında, projesiz sohbet Desktop altında durur", () => {
    kur();
    const proje = screen.getByRole("region", { name: "Mağaza" });
    expect(proje.textContent).toContain("Sepet hatası");
    expect(proje.textContent).not.toContain("Serbest sohbet");
    expect(screen.getByRole("region", { name: "Desktop" }).textContent).toContain("Serbest sohbet");
  });

  it("boş kayıtlı proje de listelenir ve içinde yeni sohbet başlatır", () => {
    const p = kur({ oturumlar: [] });
    fireEvent.click(screen.getByRole("button", { name: "Mağaza projesinde yeni sohbet başlat" }));
    expect(p.onNavigate).toHaveBeenCalledWith("project-id:p1");
  });

  it("projeyi yeniden adlandırır ve siler (sohbetler korunur uyarısıyla)", async () => {
    const p = kur();
    fireEvent.click(screen.getByRole("button", { name: "Mağaza için proje seçeneklerini aç" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Projeyi yeniden adlandır" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Proje adı" }), { target: { value: "Dükkan" } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    await waitFor(() => expect(p.onProjectRename).toHaveBeenCalledWith("p1", "Dükkan"));

    fireEvent.click(screen.getByRole("button", { name: "Mağaza için proje seçeneklerini aç" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Projeyi sil" }));
    expect(screen.getByRole("dialog").textContent).toContain("Sohbetler silinmez");
    fireEvent.click(screen.getByRole("button", { name: "Projeyi sil" }));
    await waitFor(() => expect(p.onProjectDelete).toHaveBeenCalledWith("p1"));
  });

  it("sohbeti projeye taşır ve projeden çıkarır", async () => {
    const p = kur({ projeler: [kayit, { id: "p2", name: "Blog", pinned: false, root: "", updated_at: 4 }] });
    fireEvent.click(screen.getByRole("button", { name: "Serbest sohbet sohbet seçenekleri" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Blog" }));
    await waitFor(() => expect(p.onAssign).toHaveBeenCalledWith("c2", "p2"));

    fireEvent.click(screen.getByRole("button", { name: "Sepet hatası sohbet seçenekleri" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Projeden çıkar" }));
    await waitFor(() => expect(p.onAssign).toHaveBeenCalledWith("c1", null));
  });

  it("proje desteği verilmediyse Yeni proje eski gezinmeyi kullanır", () => {
    const onNavigate = vi.fn();
    render(<Sidebar etkin={null} oturumlar={[serbest]} onSec={vi.fn()} onYeni={vi.fn()} onNavigate={onNavigate} />);
    fireEvent.click(screen.getByRole("button", { name: "Yeni proje" }));
    expect(onNavigate).toHaveBeenCalledWith("new-project");
  });
});

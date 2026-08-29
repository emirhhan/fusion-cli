import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Uygulama } from "./App";
import { ProtocolClient } from "./protocol/client";

function fakeClient() {
  let listener: ((line: string) => void) | null = null;
  const written: string[] = [];
  const client = new ProtocolClient(
    (line) => written.push(line),
    (handler) => {
      listener = handler;
    },
  );
  return { client, written, receive: (line: string) => listener?.(line) };
}

afterEach(() => {
  cleanup();
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("Uygulama", () => {
  it("soru gelince onay diyaloğunu açar", async () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    fake.receive(JSON.stringify({
      tip: "soru",
      id: "1",
      veri: { tur: "onay", arac: "write_file", argumanlar: {}, secenekler: [{ deger: "deny", etiket: "Reddet" }] },
    }));
    await waitFor(() => expect(screen.getByText(/izin verilsin mi/i)).toBeTruthy());
  });

  it("olayları konuşma akışında gösterir", async () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    fake.receive(JSON.stringify({ tip: "olay", veri: { olay: "ToolExecuted", name: "write_file" } }));
    await waitFor(() => expect(screen.getByText(/write_file/)).toBeTruthy());
  });

  it("görevi tur.calistir isteğiyle gönderir", () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "bir oyun yap" } });
    screen.getByRole("button", { name: "Gönder" }).click();
    const request = fake.written.map((line) => JSON.parse(line)).find((message) => message.ad === "tur.calistir");
    expect(request?.veri).toEqual({ gorev: "bir oyun yap" });
  });

  it("çalışan görevi kanonik tur.kes isteğiyle durdurur", () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    fireEvent.change(screen.getByRole("textbox", { name: "Mesaj" }), {
      target: { value: "uzun görev" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Gönder" }));
    fireEvent.click(screen.getByRole("button", { name: "Durdur" }));
    expect(fake.written.map((line) => JSON.parse(line)).some((message) => message.ad === "tur.kes")).toBe(
      true,
    );
  });

  it("profesyonel kabuğun tüm ana yüzeylerini bağlar", () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    expect(screen.getByRole("navigation", { name: "Ana navigasyon" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Yeni görev" })).toBeTruthy();
    expect(screen.getByRole("complementary", { name: "Denetçi" })).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "Mesaj" })).toBeTruthy();
  });

  it("tema seçimini belgeye uygular ve saklar", () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Tema" }), {
      target: { value: "dark" },
    });
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(localStorage.getItem("fusion.theme")).toBe("dark");
  });

  it("başlangıç önerisini görev girişine taşır", () => {
    const fake = fakeClient();
    render(<Uygulama istemci={fake.client} />);
    fireEvent.click(screen.getByRole("button", { name: "Yeni bir web projesi oluştur" }));
    expect(screen.getByRole("textbox", { name: "Mesaj" })).toHaveProperty(
      "value",
      "Yeni bir web projesi oluştur",
    );
  });
});

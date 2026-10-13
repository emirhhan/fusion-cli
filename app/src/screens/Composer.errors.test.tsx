import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Composer } from "./Composer";

afterEach(cleanup);

it("ek ve dikte hatalarını aynı anda birbirini örtmeden gösterir", () => {
  render(<Composer onSend={vi.fn()} attachmentError="Ek dosyası okunamadı." dictationError="Dikte izni reddedildi." />);
  expect(screen.getByText("Ek dosyası okunamadı.")).toBeTruthy();
  expect(screen.getByText("Dikte izni reddedildi.")).toBeTruthy();
});
it("komut hatası ek ve dikte hatalarının yanında bağımsız kalır", () => {
  render(<Composer onSend={vi.fn()} attachmentError="Ek hatası" dictationError="Dikte hatası" commandError="Komut hatası" />);
  for (const message of ["Ek hatası", "Dikte hatası", "Komut hatası"]) expect(screen.getByText(message)).toBeTruthy();
});

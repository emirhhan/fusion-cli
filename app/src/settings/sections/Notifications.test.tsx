import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { getNotificationPreferences, resetNotificationPreferencesCache } from "../../notifications/preferences";
import { Notifications } from "./Notifications";

afterEach(() => {
  cleanup();
  localStorage.clear();
  resetNotificationPreferencesCache();
});

describe("Ayarlar › Bildirimler", () => {
  it("üç olay anahtarı açık, ses kapalı başlar", () => {
    render(<Notifications />);
    expect((screen.getByLabelText(/Bakılan sohbetin turu bitince/) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText(/Onay ya da cevap beklerken/) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText(/Arka plandaki sohbet bitince/) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText(/kısa bir ses çal/) as HTMLInputElement).checked).toBe(false);
  });

  it("anahtar değişikliği tercihe yazılır", () => {
    render(<Notifications />);
    fireEvent.click(screen.getByLabelText(/Onay ya da cevap beklerken/));
    expect(getNotificationPreferences().onayBekliyor).toBe(false);
    fireEvent.click(screen.getByLabelText(/kısa bir ses çal/));
    expect(getNotificationPreferences().ses).toBe(true);
  });
});

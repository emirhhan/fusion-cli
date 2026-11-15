import { describe, expect, it } from "vitest";
import { normalizeNavigationDestination } from "./normalizeNavigationDestination";

describe("gezinme hedefi", () => {
  it("eski video hedefini görsel üretimine taşır", () => {
    expect(normalizeNavigationDestination("video-create")).toBe("image-create");
  });
  it.each(["image-create", "chat", "settings", "project:/proje", "project-id:42", "feedback"])("%s hedefini korur", (destination) => {
    expect(normalizeNavigationDestination(destination)).toBe(destination);
  });
});

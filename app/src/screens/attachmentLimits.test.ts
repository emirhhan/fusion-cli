import { expect, it } from "vitest";
import { mergeAttachments } from "./attachmentLimits";

it("rejects overflow without silently truncating", () => {
  const files = Array.from({ length: 21 }, (_, i) => ({ path: `/a/${i}`, name: `${i}`, kind: "file" as const }));
  expect(() => mergeAttachments([], files)).toThrow("20");
  expect(mergeAttachments([], files.slice(0, 20))).toHaveLength(20);
});
it("counts images independently and deduplicates before admission", () => {
  const image = { path: "/image.png", name: "image.png", kind: "image" as const };
  expect(mergeAttachments([image], [image])).toHaveLength(1);
  expect(() => mergeAttachments([], Array.from({ length: 9 }, (_, i) => ({ ...image, path: `/${i}.png` })))).toThrow("8");
});

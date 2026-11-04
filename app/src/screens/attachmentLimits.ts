import type { ComposerAttachment } from "./Composer";

export function mergeAttachments(current: ComposerAttachment[], additions: ComposerAttachment[]): ComposerAttachment[] {
  const merged = [...current, ...additions].filter((item, index, all) => all.findIndex((other) => other.path === item.path) === index);
  if (merged.length > 20) throw new Error("Bir turda en fazla 20 dosya eklenebilir.");
  if (merged.filter((item) => item.kind === "image").length > 8) throw new Error("Bir turda en fazla 8 görsel eklenebilir.");
  return merged;
}

import { test } from "node:test";
import assert from "node:assert/strict";
import { brandCss } from "./generate-brand-tokens.mjs";

test("aynı semantic kaynak deterministik CSS üretir ve geçersiz rengi reddeder", () => {
  const source = { schemaVersion: 1, palette: { blue: "#3b82f6" }, light: { canvas: "#ffffff" }, dark: { canvas: "#212121" } };
  assert.equal(brandCss(source), brandCss(JSON.parse(JSON.stringify(source))));
  assert.match(brandCss(source), /--fusion-blue: #3b82f6/);
  assert.match(brandCss(source), /:root\[data-theme="dark"\]/);
  assert.throws(() => brandCss({ ...source, palette: { blue: "red; color: green" } }));
  assert.throws(() => brandCss({ ...source, schemaVersion: 99 }));
});

import {expect, it} from "vitest";
import {decodeReviewFindings} from "./reviewFindings";

const item = {file: "src/a.py", line: 12, summary: "None kontrolü yok",
  failure_scenario: "boş girdi → AttributeError", verdict: "CONFIRMED", category: "correctness"};

it("ReportFindings alanlarını çözer", () => {
  expect(decodeReviewFindings([item])).toEqual([{file: "src/a.py", line: 12, summary: "None kontrolü yok",
    failureScenario: "boş girdi → AttributeError", verdict: "CONFIRMED", category: "correctness"}]);
});
it("alan yoksa kart yok, boş dizi bulgu yok demektir", () => {
  expect(decodeReviewFindings(undefined)).toBeUndefined();
  expect(decodeReviewFindings([])).toEqual([]);
});
it.each([{line: 0}, {line: "3"}, {file: ""}, {failure_scenario: 4}, {verdict: "KESIN"}])("bozuk öğe atlanır ya da alan düşer: %s", (change) => {
  const decoded = decodeReviewFindings([{...item, ...change}]) ?? [];
  if ("verdict" in change) expect(decoded[0]?.verdict).toBeUndefined();
  else expect(decoded).toEqual([]);
});
it("en çok 32 bulgu", () => {
  expect(decodeReviewFindings(Array(40).fill(item))).toHaveLength(32);
});

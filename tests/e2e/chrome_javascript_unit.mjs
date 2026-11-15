// javascript_tool (#432): sayfa betiği son ifadeyi JSON metni olarak döndürür.
import assert from "node:assert/strict";
import { SCRIPT_LIMIT, evaluateInPage } from "../../chrome-extension/core.js";

assert.deepEqual(await evaluateInPage("1 + 2", SCRIPT_LIMIT), { result: "3", truncated: false });
assert.deepEqual(await evaluateInPage("({ a: [1, 'b'] })", SCRIPT_LIMIT), { result: '{"a":[1,"b"]}', truncated: false });
assert.deepEqual(await evaluateInPage("Promise.resolve('x')", SCRIPT_LIMIT), { result: '"x"', truncated: false });
assert.deepEqual(await evaluateInPage("undefined", SCRIPT_LIMIT), { result: "undefined", truncated: false });
assert.deepEqual(await evaluateInPage("'abcdef'", 3), { result: '"ab', truncated: true });
const failed = await evaluateInPage("throw new TypeError('kötü')", SCRIPT_LIMIT);
assert.match(failed.error, /TypeError: kötü/);
console.log("chrome-javascript ✓");

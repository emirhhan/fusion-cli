import assert from "node:assert/strict";
import { test } from "node:test";
import { runtimeError } from "./check-runtime.mjs";
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve } from "node:path";
import { spawnSync } from "node:child_process";

test("App testleri desteklenen Node 22 ile çalışır", () => {
  assert.equal(runtimeError("app-tests", "22.20.0"), null);
  assert.match(runtimeError("app-tests", "26.0.0"), /Node 22/);
});

test("Kits farklı çalışma zamanı kullanır", () => {
  assert.equal(runtimeError("kits", "24.21.0"), null);
  assert.match(runtimeError("kits", "22.20.0"), /Node 24/);
});

test("Bilinmeyen yüzey ve sürüm sessizce kabul edilmez", () => {
  assert.ok(runtimeError("other", "22.20.0"));
  assert.ok(runtimeError("app-tests", "unknown"));
});

test("Kits için açıkça seçilen eski Node mevcut paketi silmeden reddedilir", () => {
  const root = mkdtempSync(resolve(tmpdir(), "fusion-runtime-test-"));
  try {
    const scripts = resolve(root, "app/scripts");
    const target = resolve(root, "app/src-tauri/resources/kits");
    mkdirSync(scripts, { recursive: true });
    mkdirSync(target, { recursive: true });
    writeFileSync(resolve(target, "sentinel"), "koru");
    for (const name of ["prepare-kits.mjs", "check-runtime.mjs"]) {
      copyFileSync(new URL(name, import.meta.url), resolve(scripts, name));
    }
    const mock = resolve(root, "mock.mjs");
    writeFileSync(mock, `import childProcess from 'node:child_process';
      import {syncBuiltinESMExports} from 'node:module';
      import {writeFileSync} from 'node:fs';
      childProcess.spawnSync=(command,args)=>{
        writeFileSync(${JSON.stringify(resolve(root, "probe.json"))},JSON.stringify({command,args}));
        return {status:0,stdout:'v22.23.3\\n'};
      };
      syncBuiltinESMExports();`);
    const result = spawnSync(process.execPath, ["--import", mock, resolve(scripts, "prepare-kits.mjs")], {
      encoding: "utf8",
      env: { ...process.env, FUSION_KITS_NODE: process.execPath, FUSION_KITS_DIR: resolve(root, "kits") },
    });
    assert.equal(result.status, 1);
    assert.match(result.stderr, /Kits Node 24/);
    assert.deepEqual(JSON.parse(readFileSync(resolve(root, "probe.json"), "utf8")), {
      command: process.execPath,
      args: ["--version"],
    });
    assert.ok(existsSync(resolve(target, "sentinel")));
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

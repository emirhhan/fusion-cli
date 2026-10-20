// App testleri ve Kits paketlemesi farklı Node sözleşmeleri kullanır.
import { pathToFileURL } from "node:url";

const APP_TEST_NODE_MAJOR = 22;
const KITS_MIN_NODE_MAJOR = 24;

export function runtimeError(surface, version) {
  const major = Number(version.split(".")[0]);
  if (!Number.isInteger(major) || major <= 0) return "Node sürümü belirlenemedi.";
  if (surface === "app-tests") {
    return major === APP_TEST_NODE_MAJOR
      ? null
      : "App testleri Node 22 ile doğrulanır. Node 22 ikilisini PATH başına ekleyip yeniden çalıştırın.";
  }
  if (surface === "kits") {
    return major >= KITS_MIN_NODE_MAJOR ? null : "Kits Node 24 veya üzerini gerektirir.";
  }
  return "Bilinmeyen çalışma zamanı yüzeyi.";
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const error = runtimeError(process.argv[2], process.versions.node);
  if (error) {
    console.error(error);
    process.exitCode = 1;
  }
}

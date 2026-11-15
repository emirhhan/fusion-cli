import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// @ts-expect-error process is a nodejs global
const host = process.env.TAURI_DEV_HOST;

// https://vite.dev/config/
export default defineConfig(async () => ({
  plugins: [react()],

  // Vite options tailored for Tauri development and only applied in `tauri dev` or `tauri build`
  //
  // 1. prevent Vite from obscuring rust errors
  clearScreen: false,
  // 2. tauri expects a fixed port, fail if that port is not available
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host
      ? {
          protocol: "ws",
          host,
          port: 1421,
        }
      : undefined,
    watch: {
      // 3. tell Vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
    },
    // Chrome eklentisi uygulamanın dışında (`../chrome-extension`); testleri onu modül
    // olarak içe aktarır. Masaüstü kısayol verisi Python paketinden gelir (P-046). Ölçüldü
    // (31 Ekim, Vite 7.3): içe aktaran modül çizgesindeyken 200 dönüyor, doğrudan ilk istekte 403;
    // izin açıkça yazılır ki çizge sırası değişse de `tauri dev` kırılmasın.
    fs: { allow: [".", "../chrome-extension", "../src/fusion_cli/config/data"] },
  },
}));

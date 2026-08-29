import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { ProtocolClient } from "./protocol/client";

/**
 * Çekirdek süreç beklenmedik şekilde kapandığında kullanıcıya gösterilecek
 * tek mesaj. `ui` katmanı henüz yok; metin burada sabit durur.
 */
const CEKIRDEK_KAPANDI_MESAJI =
  "Çekirdek beklenmedik şekilde kapandı. Uygulamayı yeniden başlatmayı deneyin.";

export default function App() {
  const [durum, setDurum] = useState("bağlanıyor…");

  useEffect(() => {
    let istemci: ProtocolClient | null = null;
    let satirDinleyiciKaldir: UnlistenFn | null = null;
    let kapandiDinleyiciKaldir: UnlistenFn | null = null;
    let etkisizlestirildi = false;

    const kur = async () => {
      await invoke("cekirdek_baslat");
      if (etkisizlestirildi) return;

      istemci = new ProtocolClient(
        (satir) => void invoke("cekirdege_yaz", { satir }),
        (f) => {
          void listen<string>("cekirdek-satir", (o) => f(o.payload)).then((kaldir) => {
            if (etkisizlestirildi) {
              kaldir();
              return;
            }
            satirDinleyiciKaldir = kaldir;
          });
        },
      );

      kapandiDinleyiciKaldir = await listen("cekirdek-kapandi", () => {
        istemci?.close(CEKIRDEK_KAPANDI_MESAJI);
        setDurum(`hata: ${CEKIRDEK_KAPANDI_MESAJI}`);
      });
      if (etkisizlestirildi) {
        kapandiDinleyiciKaldir();
        return;
      }

      const sonuc = await istemci.request("oturum.durum", {});
      setDurum(JSON.stringify(sonuc));
    };
    kur().catch((e) => setDurum(`hata: ${String(e)}`));

    return () => {
      etkisizlestirildi = true;
      satirDinleyiciKaldir?.();
      kapandiDinleyiciKaldir?.();
      istemci?.close();
    };
  }, []);

  return <pre style={{ padding: 24, fontFamily: "monospace" }}>{durum}</pre>;
}

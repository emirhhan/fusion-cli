import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { ProtocolClient } from "./protocol/client";

export default function App() {
  const [durum, setDurum] = useState("bağlanıyor…");

  useEffect(() => {
    let istemci: ProtocolClient | null = null;
    const kur = async () => {
      await invoke("cekirdek_baslat");
      istemci = new ProtocolClient(
        (satir) => void invoke("cekirdege_yaz", { satir }),
        (f) => void listen<string>("cekirdek-satir", (o) => f(o.payload)),
      );
      const sonuc = await istemci.request("oturum.durum", {});
      setDurum(JSON.stringify(sonuc));
    };
    kur().catch((e) => setDurum(`hata: ${String(e)}`));
  }, []);

  return <pre style={{ padding: 24, fontFamily: "monospace" }}>{durum}</pre>;
}

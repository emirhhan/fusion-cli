import { useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import "./PreviewPanel.css";

type PreviewKind = "image" | "audio" | "video" | "pdf" | "html" | "text";
interface PreviewAsset { yol: string; tur: PreviewKind; mime: string; boyut: number; base64: string }

export function isLocalPreviewUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  } catch {
    return false;
  }
}

function decode(payload: Record<string, unknown>): PreviewAsset {
  if (payload.ok !== true) {
    throw new Error(typeof payload.metin === "string" ? payload.metin : "Önizleme alınamadı.");
  }
  const kinds: PreviewKind[] = ["image", "audio", "video", "pdf", "html", "text"];
  if (
    typeof payload.yol !== "string" || typeof payload.tur !== "string" ||
    !kinds.includes(payload.tur as PreviewKind) || typeof payload.mime !== "string" ||
    typeof payload.boyut !== "number" || typeof payload.base64 !== "string"
  ) throw new Error("Geçersiz önizleme verisi alındı.");
  return payload as unknown as PreviewAsset;
}

function textFromBase64(value: string): string {
  const bytes = Uint8Array.from(atob(value), (character) => character.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function bytesFromBase64(value: string): Uint8Array<ArrayBuffer> {
  const raw = atob(value);
  const bytes = new Uint8Array(raw.length);
  for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index);
  return bytes;
}

export function PreviewPanel({ client, selectedPath }: { client: ProtocolClient; selectedPath: string | null }) {
  const [asset, setAsset] = useState<PreviewAsset | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [localUrl, setLocalUrl] = useState<string | null>(null);
  const [objectUrl, setObjectUrl] = useState("");

  useEffect(() => {
    let active = true;
    setAsset(null);
    setError(null);
    if (!selectedPath) return () => { active = false; };
    void client.request("proje.onizle", { yol: selectedPath })
      .then((payload) => { if (active) setAsset(decode(payload)); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { active = false; };
  }, [client, selectedPath]);

  useEffect(() => {
    setObjectUrl("");
    if (!asset || asset.tur === "html" || asset.tur === "text") return;
    const url = URL.createObjectURL(new Blob([bytesFromBase64(asset.base64)], { type: asset.mime }));
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [asset]);

  const openLocal = () => {
    const value = input.trim();
    if (!isLocalPreviewUrl(value)) {
      setLocalUrl(null);
      setError("Güvenlik için uygulama içine yalnız localhost adresleri açılabilir.");
      return;
    }
    setError(null);
    setLocalUrl(value);
  };

  return (
    <div className="preview-panel">
      <form onSubmit={(event) => { event.preventDefault(); openLocal(); }}>
        <label htmlFor="local-preview-url">Yerel önizleme adresi</label>
        <div>
          <input id="local-preview-url" onChange={(event) => setInput(event.target.value)} placeholder="http://localhost:5173" value={input} />
          <button type="submit">Adresi aç</button>
        </div>
      </form>
      {error && <p className="preview-panel__error" role="alert">{error}</p>}
      {localUrl ? (
        <iframe className="preview-panel__frame" sandbox="allow-forms allow-modals allow-pointer-lock allow-same-origin allow-scripts" src={localUrl} title="Yerel geliştirme önizlemesi" />
      ) : asset ? (
        <div className="preview-panel__asset">
          <header><strong>{asset.yol}</strong><span>{asset.mime} · {asset.boyut.toLocaleString("tr-TR")} bayt</span></header>
          {asset.tur === "image" && objectUrl && <img alt={`${asset.yol} önizlemesi`} src={objectUrl} />}
          {asset.tur === "audio" && objectUrl && <audio controls src={objectUrl}>Ses önizlemesi desteklenmiyor.</audio>}
          {asset.tur === "video" && objectUrl && <video controls src={objectUrl}>Video önizlemesi desteklenmiyor.</video>}
          {asset.tur === "pdf" && objectUrl && <iframe className="preview-panel__frame" sandbox="" src={objectUrl} title={`${asset.yol} PDF önizlemesi`} />}
          {asset.tur === "html" && <iframe className="preview-panel__frame" sandbox="" srcDoc={textFromBase64(asset.base64)} title={`${asset.yol} HTML önizlemesi`} />}
          {asset.tur === "text" && <pre>{textFromBase64(asset.base64)}</pre>}
        </div>
      ) : !error && <p className="preview-panel__empty">Dosyalardan bir asset seç veya çalışan yerel sunucunun adresini gir.</p>}
    </div>
  );
}

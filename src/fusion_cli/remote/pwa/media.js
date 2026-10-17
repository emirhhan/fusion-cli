import { h } from "./dom.js";

const cache = new Map();
const IMAGE_MD = /!\[([^\]]*)\]\((?:<([^>]+)>|([^)\s]+))\)/g;
export const MAX_ATTACH_BYTES = 640 * 1024; // sunucu sınırı 700 KB; base64 ve zarf payı için altında
const MAX_SIDE = 1280;

// Telefondan gelen görseli küçültür: en uzun kenar 1280 px, JPEG; sınırı aşarsa kaliteyi düşürür.
export async function prepareAttachment(file) {
  if (!file.type.startsWith("image/")) {
    if (file.size > MAX_ATTACH_BYTES) throw new Error("Dosya en fazla 640 KB olabilir.");
    return { name: file.name, kind: "file", dataBase64: await toBase64(file), preview: null };
  }
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  for (const quality of [0.8, 0.65, 0.5, 0.35]) {
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
    if (blob && blob.size <= MAX_ATTACH_BYTES) {
      const name = `${file.name.replace(/\.[^.]+$/, "") || "foto"}.jpg`;
      return { name, kind: "image", dataBase64: await toBase64(blob), preview: URL.createObjectURL(blob) };
    }
  }
  throw new Error("Görsel küçültülemedi; daha küçük bir görsel seç.");
}

async function toBase64(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

// Sohbet metnini düğümlere çevirir: düz metin + `![alt](<yol>)` görselleri (media.get ile yüklenir).
export function renderRichText(text, rpc) {
  const nodes = [];
  let last = 0;
  for (const match of text.matchAll(IMAGE_MD)) {
    if (match.index > last) nodes.push(text.slice(last, match.index));
    nodes.push(imageNode(match[2] ?? match[3], match[1], rpc));
    last = match.index + match[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function imageNode(path, alt, rpc) {
  const img = h("img", { class: "gen", alt: alt || "Görsel", loading: "lazy" });
  const frame = h("button", { class: "gen-frame", type: "button", "aria-label": alt || "Görseli büyüt" }, img);
  frame.addEventListener("click", () => frame.classList.toggle("big"));
  void load(path, rpc).then((src) => { img.src = src; }).catch((error) => {
    frame.replaceChildren(h("span", { class: "muted small" }, error.message || "Görsel açılamadı"));
  });
  return frame;
}

async function load(path, rpc) {
  if (cache.has(path)) return cache.get(path);
  const result = await rpc("media.get", { path });
  if (!result.ok) throw new Error(result.message || "Görsel açılamadı");
  const src = `data:${result.data.mediaType};base64,${result.data.dataBase64}`;
  cache.set(path, src);
  return src;
}

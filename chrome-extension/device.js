// Bu tarayıcının Fusion köprüsündeki kimliği (#432): birden çok tarayıcı bağlanınca
// Fusion hangisine komut göndereceğini bu kimlikle seçer. Kimlik bir kez üretilir ve
// `chrome.storage.local`'da saklanır; ad tarayıcının markasıdır (Chrome, Edge, Brave…).
export const DEVICE_KEY = "fusionDevice";

const BRANDS = [
  ["Microsoft Edge", "Edge"], ["Brave", "Brave"], ["Opera", "Opera"], ["Vivaldi", "Vivaldi"],
  ["Arc", "Arc"], ["Google Chrome", "Chrome"], ["Chromium", "Chromium"],
];

/** `navigator.userAgentData.brands` içinden tarayıcı adı. */
export function browserName(brands = globalThis.navigator?.userAgentData?.brands || []) {
  const names = brands.map((brand) => String(brand.brand || ""));
  for (const [needle, label] of BRANDS) if (names.some((name) => name.includes(needle))) return label;
  return "Chrome";
}

function newId() {
  const bytes = crypto.getRandomValues(new Uint8Array(9));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** `{ id, ad }`; ilk çağrıda üretilip saklanır. */
export async function deviceIdentity(storage = chrome.storage.local) {
  const stored = (await storage.get(DEVICE_KEY).catch(() => ({})))[DEVICE_KEY];
  if (stored && /^[A-Za-z0-9_-]{1,64}$/.test(String(stored.id || ""))) return { id: stored.id, ad: browserName() };
  const identity = { id: `${browserName().toLowerCase()}-${newId()}`, ad: browserName() };
  await storage.set({ [DEVICE_KEY]: identity }).catch(() => undefined);
  return identity;
}

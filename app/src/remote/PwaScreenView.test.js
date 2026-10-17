import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/dom";
const fake = vi.hoisted(() => ({ start: vi.fn(async () => {}), stop: vi.fn(async () => {}), detach: vi.fn(), setVisible: vi.fn(), options: null }));
vi.mock("../../../src/fusion_cli/remote/pwa/screen-stream.js", () => ({ createScreenStream: vi.fn((options) => { fake.options = options; return fake; }) }));
import { createScreenView } from "../../../src/fusion_cli/remote/pwa/screen-view.js";
let view;
beforeEach(() => {
  vi.clearAllMocks();
  document.body.innerHTML = '<section><div id="ekranKutu" class="empty-screen"><img id="ekranKare"></div><p id="ekranDurum"></p><div><button id="ekranIste">İzlemeyi başlat</button><button id="ekranDur">Durdur</button></div></section>';
});
afterEach(() => { view?.close(); document.body.innerHTML = ""; });
function setup(remembered = false, state = "none") {
  const rpc = vi.fn(async (method) => ({ ok: true, data: method === "screen.status" ? { state, remembered } : { windows: [], tabs: [] } }));
  view = createScreenView({ rpc, onAuth: vi.fn(), toast: vi.fn() });
  return rpc;
}
it("ilk istekte telefon içinde onay ve varsayılan hatırlama seçeneğini gösterir", async () => {
  setup(); await view.open();
  fireEvent.click(screen.getByText("İzlemeyi başlat"));
  const approve = await screen.findByText("Onayla ve izlemeyi başlat");
  expect(screen.getByRole("checkbox").checked).toBe(true);
  expect(fake.start).toHaveBeenCalledTimes(1);
  fireEvent.click(approve);
  await waitFor(() => expect(fake.start).toHaveBeenCalledWith({ request: true, remember: true, confirmed: true }));
});
it("hatırlanan cihazı yeniden onay sormadan başlatır", async () => {
  setup(true); await view.open();
  fireEvent.click(screen.getByText("İzlemeyi başlat"));
  await waitFor(() => expect(fake.start).toHaveBeenCalledWith({ request: true }));
  expect(screen.queryByRole("region", { name: "Ekran izleme izni" })).toBeNull();
});
it("hatırlama seçimi kapatılabilir; durdur sunucuyu çağırır, görünüm kapatma yalnız ayırır", async () => {
  setup(); await view.open();
  fireEvent.click(screen.getByText("İzlemeyi başlat"));
  await screen.findByText("Onayla ve izlemeyi başlat");
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByText("Onayla ve izlemeyi başlat"));
  expect(fake.start).toHaveBeenCalledWith({ request: true, remember: false, confirmed: true });
  fireEvent.click(screen.getByText("Durdur"));
  expect(fake.stop).toHaveBeenCalledTimes(1);
  view.close(); expect(fake.detach).toHaveBeenCalledTimes(1);
});
it("oranı yalnız gerçek görüntü yüklendiğinde uygular ve eski kareyi kapatırken temizler", async () => {
  setup(); await view.open();
  fake.options.onFrame({ jpegBase64: "YWJj" });
  const image = document.getElementById("ekranKare");
  const box = document.getElementById("ekranKutu");
  expect(box.style.aspectRatio).toBe("");
  Object.defineProperties(image, { naturalWidth: { value: 1920 }, naturalHeight: { value: 1080 } });
  fireEvent.load(image);
  expect(box.style.aspectRatio).toBe("1920 / 1080");
  view.close(); expect(image.hasAttribute("src")).toBe(false);
});

it("bekleyen eski izni telefonda açık onayla tamamlar", async () => {
  setup(false, "pending"); await view.open();
  expect(document.getElementById("ekranIste").hidden).toBe(false);
  fireEvent.click(document.getElementById("ekranIste"));
  await screen.findByText("Onayla ve izlemeyi başlat");
  expect(fake.start).toHaveBeenCalledTimes(0);
  fireEvent.click(screen.getByText("Onayla ve izlemeyi başlat"));
  expect(fake.start).toHaveBeenCalledWith({ request: true, remember: true, confirmed: true });
});

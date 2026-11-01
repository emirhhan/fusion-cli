/** Eski üretim hedefini çalışan görsel ekranına yönlendirir. */
export function normalizeNavigationDestination(destination: string): string {
  return destination === "video-create" ? "image-create" : destination;
}

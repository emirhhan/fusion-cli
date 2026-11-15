/** Yalnız masaüstünün başlattığı çocuğun dinleme makbuzu; model/anahtar verisi içermez. */
export function readinessNotice(
  env: Record<string, string | undefined>,
  port: number,
  pid: number,
): string | undefined {
  const nonce = env.KITS_DESKTOP_READY_NONCE;
  if (!nonce || !/^[0-9a-f]{32}$/.test(nonce)) return undefined;
  if (
    !Number.isInteger(port) ||
    port < 1 ||
    port > 65535 ||
    !Number.isInteger(pid) ||
    pid < 1
  )
    return undefined;
  return JSON.stringify({ fusion_kits_ready: 1, nonce, port, pid });
}

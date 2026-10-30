/**
 * Doğrulanmamış / hazır olmayan model seçimi için "bu oturumda hatırla" belleği (U1-45, U2-49).
 *
 * Uygulama açık kaldığı sürece geçerlidir, diske yazılmaz: kullanıcı aynı modeli her seçişinde
 * yeniden sorulmaz, ama uygulama yeniden açılınca onay sıfırlanır.
 */
const approved = new Set<string>();

export function isModelApproved(key: string): boolean {
  return approved.has(key);
}

export function approveModel(key: string): void {
  approved.add(key);
}

/** Yalnız testler için. */
export function resetModelApprovals(): void {
  approved.clear();
}

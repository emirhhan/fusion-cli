/**
 * Proje kökü değerlendirmesi.
 *
 * Her oturum kökü "proje" değildir. Uygulamadan açılan bir oturumun kökü
 * dosya sistemi kökü ("/") ya da doğrudan ev dizini olabiliyor; bunlar kenar
 * çubuğunda adı "/" olan ya da kullanıcı adını taşıyan anlamsız satırlara
 * dönüşüyordu. Bir kök, en az iki seviye derinlikteyse projedir.
 */

/** Yoldaki boş olmayan parçalar. Hem POSIX hem Windows ayracını kabul eder. */
function parts(root: string): string[] {
  return root.split(/[\\/]/).filter(Boolean);
}

/** Kökü olduğu gibi gösterilecek proje adı. */
export function projectName(root: string): string {
  const bolumler = parts(root);
  return bolumler[bolumler.length - 1] ?? root;
}

/** Ev dizini kalıpları: `/Users/<ad>`, `/home/<ad>` ve Windows karşılığı. */
const HOME_PARENTS = new Set(["users", "home"]);

export function isProjectRoot(root: string): boolean {
  let bolumler = parts(root.trim());
  // Windows sürücü harfi ("C:") yolun seviyesi değildir: `C:\Users\ad` ev dizinidir (U4-57).
  if (bolumler.length > 0 && /^[A-Za-z]:$/.test(bolumler[0])) bolumler = bolumler.slice(1);
  if (bolumler.length === 0) return false;
  // "C:\" tek parçadır ve sürücü köküdür.
  if (bolumler.length === 1) return false;
  if (bolumler.length === 2 && HOME_PARENTS.has(bolumler[0].toLowerCase())) return false;
  return true;
}

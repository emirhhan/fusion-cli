import { lookup } from 'node:dns/promises';
import { isIP } from 'node:net';

/** Kit tarayıcısı yalnız herkese açık internete çıkar: kullanıcının Mac'indeki
 * servisler (Kits'in kendi arayüzü, Fusion geçidi) ve yerel ağ cihazları
 * kapalıdır. Sayfadaki yönlendirme ve alt istekler de aynı denetimden geçer. */
const PRIVATE_V4 = [
  [0, 8],
  [10, 8],
  [100, 10], // 100.64/10 taşıyıcı NAT
  [127, 8],
  [169, 254],
  [172, 16],
  [192, 168],
] as const;

function privateV4(address: string) {
  const [a, b] = address.split('.').map(Number);
  return PRIVATE_V4.some(([first, second]) => {
    if (a !== first) return false;
    if (first === 172) return b >= 16 && b <= 31;
    if (first === 100) return b >= 64 && b <= 127;
    if (first === 169 || first === 192) return b === second;
    return true;
  });
}

export function isPrivateAddress(address: string) {
  const bare = address.replace(/^\[|\]$/g, '').toLowerCase();
  if (isIP(bare) === 4) return privateV4(bare);
  if (isIP(bare) === 6) {
    const mapped = bare.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/);
    if (mapped) return privateV4(mapped[1]);
    return (
      bare === '::' ||
      bare === '::1' ||
      bare.startsWith('fc') ||
      bare.startsWith('fd') ||
      bare.startsWith('fe80')
    );
  }
  return false;
}

const PRIVATE_NAMES =
  /^(localhost|.*\.localhost|.*\.local|.*\.internal|.*\.lan)$/i;
const resolved = new Map<string, Promise<boolean>>();

/** Ad çözülür; herhangi bir adresi yerelse istek reddedilir (DNS ile yerel
 * adrese yönlendirme dahil). Sonuç süreç boyunca önbellekte tutulur. */
export function isPrivateHost(hostname: string): Promise<boolean> {
  const host = hostname.replace(/^\[|\]$/g, '').toLowerCase();
  if (!host) return Promise.resolve(true);
  if (isIP(host)) return Promise.resolve(isPrivateAddress(host));
  if (PRIVATE_NAMES.test(host)) return Promise.resolve(true);
  let pending = resolved.get(host);
  if (!pending) {
    pending = lookup(host, { all: true }).then(
      (addresses) => addresses.some((item) => isPrivateAddress(item.address)),
      // Çözülemeyen ad: tarayıcı zaten açamaz; denetim engel olmaz.
      () => false,
    );
    resolved.set(host, pending);
  }
  return pending;
}

export const PRIVATE_HOST_MESSAGE =
  'Kit bilgisayarı yerel adreslere (bu Mac, yerel ağ) gidemez; yalnız herkese açık sayfalar açılabilir.';

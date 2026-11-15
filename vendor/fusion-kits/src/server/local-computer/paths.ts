import { lstat, realpath } from 'node:fs/promises';
import { dirname, isAbsolute, join, relative, sep } from 'node:path';
import { OperationError } from './errors.js';

const ESCAPE = 'Yol Kit klasörünün dışına çıkıyor.';

function isInside(root: string, target: string) {
  const rel = relative(root, target);
  return rel !== '..' && !rel.startsWith(`..${sep}`) && !isAbsolute(rel);
}

/**
 * Göreli yolu Kit klasörüne bağlar. Var olan en derin üst dizinin realpath'i
 * klasör içinde kalmalı; sembolik bağlarla dışarı kaçış reddedilir.
 * `root` önceden realpath ile çözülmüş olmalıdır.
 */
export async function resolveInside(root: string, rel: string) {
  if (isAbsolute(rel) || rel.includes('\0')) throw new OperationError(ESCAPE);
  if (rel.split(/[\\/]/).includes('..')) throw new OperationError(ESCAPE);
  const target = join(root, rel);
  let probe = target;
  for (;;) {
    try {
      const real = await realpath(probe);
      if (!isInside(root, real)) throw new OperationError(ESCAPE);
      return join(real, relative(probe, target));
    } catch (error) {
      if (error instanceof OperationError) throw error;
      const code = (error as NodeJS.ErrnoException).code;
      if (code !== 'ENOENT' && code !== 'ENOTDIR') throw error;
      // Kırık sembolik bağ da dışarı işaret edebilir.
      const info = await lstat(probe).catch(() => undefined);
      if (info?.isSymbolicLink()) throw new OperationError(ESCAPE);
      const parent = dirname(probe);
      if (parent === probe) throw new OperationError(ESCAPE);
      probe = parent;
    }
  }
}

import { constants } from 'node:fs';
import { mkdir, open, readdir, realpath, stat } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { OperationError } from './errors.js';
import { resolveInside } from './paths.js';

export const MAX_READ_BYTES = 200_000;
export const MAX_FILE_BYTES = 5_000_000;
export const MAX_LIST_ENTRIES = 500;

function missing(error: unknown): never {
  const code = (error as NodeJS.ErrnoException).code;
  if (code === 'ENOENT' || code === 'ENOTDIR')
    throw new OperationError('Dosya veya klasör bulunamadı.');
  if (code === 'ELOOP')
    throw new OperationError('Sembolik bağlar üzerinden yazılamaz.');
  throw error;
}

export async function listFiles(root: string, path: string) {
  const dir = await resolveInside(root, path);
  try {
    const names = (await readdir(dir)).sort().slice(0, MAX_LIST_ENTRIES);
    const entries = await Promise.all(
      names.map(async (name) => {
        const info = await stat(join(dir, name)).catch(() => undefined);
        return {
          name,
          type: info?.isDirectory() ? 'directory' : 'file',
          size: info?.isFile() ? info.size : 0,
        };
      }),
    );
    return { path, entries };
  } catch (error) {
    return missing(error);
  }
}

export async function readFileText(root: string, path: string) {
  const file = await resolveInside(root, path);
  try {
    const handle = await open(file, constants.O_RDONLY);
    try {
      const info = await handle.stat();
      if (!info.isFile()) throw new OperationError('Bu bir dosya değil.');
      const buffer = Buffer.alloc(Math.min(info.size, MAX_READ_BYTES));
      const { bytesRead } = await handle.read(buffer, 0, buffer.length, 0);
      return {
        path,
        text: buffer.subarray(0, bytesRead).toString('utf8'),
        size: info.size,
        truncated: info.size > MAX_READ_BYTES,
      };
    } finally {
      await handle.close();
    }
  } catch (error) {
    return missing(error);
  }
}

export async function writeFileText(
  root: string,
  path: string,
  contents: string,
  append = false,
) {
  const file = await resolveInside(root, path);
  if (file === root) throw new OperationError('Klasörün kendisine yazılamaz.');
  await mkdir(dirname(file), { recursive: true });
  // mkdir sonrası üst dizin hâlâ klasör içinde mi?
  if ((await realpath(dirname(file))) !== dirname(file))
    await resolveInside(root, path);
  const bytes = Buffer.from(contents, 'utf8');
  try {
    // O_NOFOLLOW: son bileşen sembolik bağ ise açılmaz.
    const handle = await open(
      file,
      constants.O_WRONLY |
        constants.O_CREAT |
        constants.O_NOFOLLOW |
        (append ? constants.O_APPEND : constants.O_TRUNC),
      0o644,
    );
    try {
      const info = await handle.stat();
      if (!info.isFile()) throw new OperationError('Bu bir dosya değil.');
      if ((append ? info.size : 0) + bytes.length > MAX_FILE_BYTES)
        throw new OperationError('Dosya boyut sınırını aşıyor (5 MB).');
      await handle.write(bytes);
    } finally {
      await handle.close();
    }
  } catch (error) {
    return missing(error);
  }
  return { path, bytes: bytes.length, append };
}

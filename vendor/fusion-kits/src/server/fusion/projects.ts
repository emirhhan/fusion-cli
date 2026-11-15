import { realpathSync, statSync } from 'node:fs';
import { homedir } from 'node:os';
import { isAbsolute, parse, relative, resolve } from 'node:path';

/** Kullanıcının Kits ekranından eklediği proje kökleri (kalıcı depo). */
export interface UserProjects {
  fusionProjects(): Record<string, string>;
  saveFusionProject(name: string, path: string): void;
  deleteFusionProject(name: string): boolean;
}

export interface ProjectEntry {
  name: string;
  path: string;
  /** env: sunucu yapılandırması (silinemez); user: ekrandan eklendi. */
  source: 'env' | 'user';
}

export const PROJECT_NAME = /^[\p{L}\p{N}_.-]{1,64}$/u;

const inside = (parent: string, child: string) => {
  const rel = relative(parent, child);
  return rel === '' || (!rel.startsWith('..') && !isAbsolute(rel));
};

/**
 * Eklenecek klasörü doğrular ve gerçek yolunu döndürür.
 *
 * Kits'in kendi kodu, çalışma verisi ya da ev/kök dizininin tamamı proje
 * olamaz: sohbetteki model "bütün diskte çalış" diyememeli ve Kits kendi
 * kodunu değiştirememeli.
 */
export function validateProjectPath(
  path: string,
  guard: { fusionHome: string; kitsRoot: string; home?: string },
): string {
  if (!isAbsolute(path)) throw new Error('Klasör yolu mutlak olmalı.');
  let real: string;
  try {
    real = realpathSync(path);
  } catch {
    throw new Error('Klasör bulunamadı.');
  }
  if (!statSync(real).isDirectory()) throw new Error('Bu bir klasör değil.');
  const home = resolve(guard.home ?? homedir());
  if (real === parse(real).root || real === home)
    throw new Error(
      'Diskin ya da ev dizininin tamamı eklenemez; bir proje klasörü seç.',
    );
  for (const blocked of [guard.fusionHome, guard.kitsRoot]) {
    const target = resolve(blocked);
    if (inside(target, real) || inside(real, target))
      throw new Error('Kits kendi kodunu veya çalışma verisini proje yapamaz.');
  }
  return real;
}

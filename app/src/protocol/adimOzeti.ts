import type { OlayAdimi } from "./olayMetni";

/**
 * Biten araç adımlarının tek satırlık özeti ve canlı durum satırının metinleri.
 *
 * Claude bir araç grubunu tek satırda toplar: "Ran 3 commands, read 4 files,
 * searched code ›". Fusion eskiden "5 adım · src/app.py okunuyor" yazıyordu;
 * son adımın adı grubun ne yaptığını anlatmıyor, kullanıcı satırı açmadan işin
 * ne olduğunu göremiyordu. Özet artık araç TÜRLERİNİ sayar.
 */

type AdimTuru =
  | "komut"
  | "okuma"
  | "bulma"
  | "arama"
  | "duzenleme"
  | "web"
  | "tarayici"
  | "masaustu"
  | "ogretmen"
  | "diger";

/** Araç adı → özet türü. Listede olmayan araç "diger" sayılır. */
const ARAC_TURU: Record<string, AdimTuru> = {
  run_shell: "komut",
  git: "komut",
  read_file: "okuma",
  list_dir: "bulma",
  glob: "bulma",
  search_code: "arama",
  write_file: "duzenleme",
  edit_file: "duzenleme",
  multi_edit: "duzenleme",
  scaffold_web: "duzenleme",
  web_search: "web",
  web_fetch: "web",
  download_file: "web",
  ask_teacher: "ogretmen",
};

/** Kendi kartı olan araçlar özete girmez (görev listesi ayrı kartta durur). */
const OZETE_GIRMEYEN = new Set(["todo_write"]);

function aracTuru(arac: string): AdimTuru {
  if (ARAC_TURU[arac]) return ARAC_TURU[arac];
  if (arac.startsWith("chrome_") || arac.startsWith("browser_")) return "tarayici";
  if (arac.startsWith("desktop_")) return "masaustu";
  return "diger";
}

/** Tür başına cümle; tek hedefli okuma/düzenlemede dosyanın adı yazılır. */
function cumle(tur: AdimTuru, adet: number, tekHedef: string | undefined): string {
  switch (tur) {
    case "komut":
      return adet === 1 ? "komut çalıştırıldı" : `${adet} komut çalıştırıldı`;
    case "okuma":
      return adet === 1 && tekHedef ? `${tekHedef} okundu` : `${adet} dosya okundu`;
    case "bulma":
      return "dosyalar bulundu";
    case "arama":
      return "kod arandı";
    case "duzenleme":
      return adet === 1 && tekHedef ? `${tekHedef} düzenlendi` : `${adet} dosya düzenlendi`;
    case "web":
      return adet === 1 ? "web'e bakıldı" : `${adet} web kaynağına bakıldı`;
    case "tarayici":
      return `tarayıcıda ${adet} işlem yapıldı`;
    case "masaustu":
      return `masaüstünde ${adet} işlem yapıldı`;
    case "ogretmen":
      return "öğretmene danışıldı";
    case "diger":
      return adet === 1 ? "bir araç kullanıldı" : `${adet} araç kullanıldı`;
  }
}

function ilkHarfBuyuk(metin: string): string {
  return metin ? metin.charAt(0).toLocaleUpperCase("tr-TR") + metin.slice(1) : metin;
}

/**
 * "3 komut çalıştırıldı, 4 dosya okundu, kod arandı" — türler ilk görüldükleri
 * sırayla. Araç olmayan kalıcı adımlar (hafıza, resmi kaynak) kendi metniyle
 * eklenir.
 */
export function adimOzeti(adimlar: OlayAdimi[]): string {
  const sayac = new Map<AdimTuru, { adet: number; hedefler: Set<string> }>();
  const serbest: string[] = [];
  for (const adim of adimlar) {
    if (!adim.arac) {
      if (adim.kalici && !serbest.includes(adim.metin)) serbest.push(adim.metin);
      continue;
    }
    if (OZETE_GIRMEYEN.has(adim.arac)) continue;
    const tur = aracTuru(adim.arac);
    const kayit = sayac.get(tur) ?? { adet: 0, hedefler: new Set<string>() };
    kayit.adet += 1;
    if (adim.ayrinti) kayit.hedefler.add(adim.ayrinti);
    sayac.set(tur, kayit);
  }
  const parcalar = [...sayac.entries()].map(([tur, { adet, hedefler }]) =>
    cumle(tur, adet, hedefler.size === 1 ? [...hedefler][0] : undefined),
  );
  const tumu = [...parcalar, ...serbest.map((metin) => metin.toLocaleLowerCase("tr-TR"))];
  return ilkHarfBuyuk(tumu.join(", "));
}

/** 42 → "42 sn", 554 → "9 dk 14 sn", 3720 → "1 sa 2 dk". */
export function sureMetni(saniye: number): string {
  const tam = Math.max(0, Math.floor(saniye));
  if (tam < 60) return `${tam} sn`;
  const dakika = Math.floor(tam / 60);
  if (dakika < 60) return `${dakika} dk ${tam % 60} sn`;
  return `${Math.floor(dakika / 60)} sa ${dakika % 60} dk`;
}

/** 850 → "850 token", 2034 → "2,0 bin token". */
export function tokenMetni(adet: number): string {
  if (adet < 1000) return `${adet} token`;
  const bin = (adet / 1000).toLocaleString("tr-TR", {
    maximumFractionDigits: 1,
    minimumFractionDigits: 1,
  });
  return `${bin} bin token`;
}

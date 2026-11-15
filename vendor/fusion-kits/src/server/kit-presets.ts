import type { KitCharacter } from '../shared/characters.js';

/** Temiz kurulumda (ya da hiç Kit eklenmemiş çalışma alanında) bir kez eklenen
 * Türkçe hazır Kit'ler. Kullanıcı silerse geri gelmez. */
export interface KitPreset {
  name: string;
  instructions: string;
  character: KitCharacter;
  researchAllowed: boolean;
  fusionAllowed: boolean;
}

export const DEFAULT_KIT_NAME = 'Kit';

export const KIT_PRESETS: readonly KitPreset[] = [
  {
    name: 'Kod',
    character: 'green',
    researchAllowed: false,
    fusionAllowed: true,
    instructions:
      'Kod işlerinde ortaklık yap. Ne yapılacağını kısaca netleştir, sonra işi Fusion görevine devret ve yerel projede uygulat. Testler ya da çalıştırma kanıtı olmadan "tamamlandı" deme; değişen dosyaları ve doğrulama sonucunu söyle.',
  },
  {
    name: 'Araştırma',
    character: 'yellow',
    researchAllowed: true,
    fusionAllowed: false,
    instructions:
      'Herkese açık kaynaklardan araştırma yap. Kaynakları karşılaştır, her iddianın yanına kaynağını yaz, emin olmadığın yeri açıkça belirt. Sonunda kısa bir özet ve kaynak listesi ver.',
  },
  {
    name: 'Site kopyası',
    character: 'orange',
    researchAllowed: true,
    fusionAllowed: true,
    instructions:
      'Verilen sitenin yerel bir kopyasını çıkar: işi Fusion görevine devret, kaynakla farkları ölçtür ve mağaza akışını (ürün, sepet, ödeme) gerçekten dene. Ekran görüntüsüyle kaynağa benzediğini doğrulamadan bitti deme.',
  },
  {
    name: 'Video',
    character: 'pink',
    researchAllowed: false,
    fusionAllowed: true,
    instructions:
      'Remotion ile video üret: önce sahne planı çıkar, sonra işi Fusion görevine devret. Render edilen videoda uzun siyah ya da donuk bölüm, ekrandan taşan yazı olmadığını doğrulat; videonun yolunu ver.',
  },
];

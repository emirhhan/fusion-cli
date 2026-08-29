# Fusion Core System — Marka Uygulaması

Bu klasör markanın koddaki karşılığını belgeler. Uygulanan kaynak:
`Fusion_Core_System_REFERENCE_EXACT_Pack` (onaylı referans).

## Palet

| Ad | Değer | Nerede |
|---|---|---|
| Obsidian | `#0B0A0D` | Koyu temada kenar çubuğu; açık temada mürekkep ve birincil kontrol |
| Carbon | `#14181D` | Koyu temada içerik zemini |
| Soft White | `#F3F5F6` | Koyu temada mürekkep |
| Signal Green | `#A8FF3E` | Vurgu — her iki temada da aynı |
| Signal Deep | `#446B00` | Yalnız açık temada, vurgulu METİN ve odak halkası |

**Ölçülmüş kontrastlar:** Soft White / Carbon 16.30:1 · ikincil metin / Carbon
7.05:1 · Signal Green / Obsidian 16.02:1. Üçü de WCAG AA'nın üstünde.

**Signal Green beyaz üstünde 1.23:1 verir.** Bu yüzden açık temada asla metin
rengi değildir: dolgu olarak kullanılır (üstüne Obsidian yazılır) ya da metin
gerektiğinde Signal Deep'e düşülür. Bu kural `theme/tokens.test.ts` ile kilitli.

## İşaret

`app/src/brand/Logo.tsx`. İşaret negatif alanla çalışır: disk doludur, "F" ve
ayırıcı kanallar zeminin rengidir, alt parça Signal Green'dir.

Referansın 888 piksellik kaynağı piksel taramasıyla ölçüldü ve **temiz
geometriye** çevrildi (daire + dik kanallar + iki ışınsal yarık). Referansla
piksel örtüşmesi **%91.7**'dir; kalan fark kaynak PNG'nin kendi kenar
gürültüsünden gelir.

Referans paketindeki `*-TRACED-VECTOR.svg` dosyaları KULLANILMADI ve
kullanılmamalıdır: her noktası 1 piksellik merdiven basamağıdır, gradyan
gömülüdür ve yeşil parçanın `d` özniteliği boştur. Karşılaştırma için ölçüm
kaynağı `referans-sembol-8x.png` olarak burada saklanır.

Mürekkep temaya göre döner (açık temada Obsidian, koyu temada Soft White);
Signal Green sabittir — markanın değişmeyeni odur.

## Tipografi

Marka tipografisi **Satoshi**'dir. Uygulama internete çıkmaz ve font dosyası
depoya gömülmedi; Satoshi kurulu sistemlerde kullanılır, değilse yığın sessizce
Inter/sistem yazı tipine düşer. Font dosyasını gömmek istenirse tek değişecek
yer `theme/tokens.css` içindeki `--font-sans` ve bir `@font-face` bloğudur.

## İkonlar

`app/src-tauri/icons/` altındaki tüm boyutlar (macOS `.icns`, Windows `.ico`,
PNG'ler ve Windows Store kutucukları) işaretten üretilir; elle çizilmez.
Uygulama ikonu: Obsidian yuvarlatılmış kare üzerinde işaret.

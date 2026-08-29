/**
 * Fusion Core System marka işareti.
 *
 * Onaylı referanstan (`Fusion_Core_System_REFERENCE_EXACT_Pack`) 888 piksellik
 * kaynağın piksel taramasıyla ÖLÇÜLÜP temiz geometriye çevrildi: daire, dik
 * kanallar ve iki ışınsal yarık. Referansla piksel örtüşmesi %91.7'dir; kalan
 * fark kaynağın kendi kenar gürültüsünden gelir. Trace edilmiş merdiven yollar
 * ve gömülü gradyanlar bilerek KULLANILMADI — onlar her boyutta bulanıklaşır.
 *
 * Kompozisyon: disk, negatif alanda "F" ve alt parçadaki Signal Green pay.
 * Renkler `brand.css`'teki `--logo-*` değişkenlerinden gelir; bileşen ham renk
 * kodu taşımaz, böylece açık ve koyu temada aynı dosya doğru görünür.
 */
export interface LogoProps {
  /** Kenar uzunluğu (px). İşaret kare oranlıdır. */
  size?: number;
  /** Erişilebilir ad. Yalnız işaretin tek başına anlam taşıdığı yerde verilir. */
  title?: string;
}

/** Maske kimlikleri sayfada benzersiz olmalı; aynı anda birden çok logo olabilir. */
let counter = 0;

export function Logo({ size = 24, title }: LogoProps) {
  const id = `fusion-logo-${(counter += 1)}`;
  return (
    <svg
      aria-hidden={title ? undefined : true}
      className="fusion-logo"
      height={size}
      role={title ? "img" : undefined}
      viewBox="0 0 64 64"
      width={size}
      xmlns="http://www.w3.org/2000/svg"
    >
      {title ? <title>{title}</title> : null}
      <defs>
        <mask id={`${id}-cut`}>
          <rect width="64" height="64" fill="#000" />
          <circle cx="32" cy="32" r="30" fill="#fff" />
          <path d="M15.6 17.3 H25.4 V64 H15.6 Z" fill="#000" />
          <path d="M16.5 17.3 H43.2 V27.5 H24.6 A6 6 0 0 0 18.6 33.5 V17.3 Z" fill="#000" />
          <path d="M15.6 33.4 H43.5 V42.9 H15.6 Z" fill="#000" />
          <path d="M5.3 26.5 H15.6 V30.6 H5.3 Z" fill="#000" />
          <path d="M40.6 21.4 L46.8 9.6 L49.8 11.4 L43.6 23.2 Z" fill="#000" />
          <path d="M42.6 41.6 L55.2 52.4 L52.8 55.2 L40.2 44.4 Z" fill="#000" />
        </mask>
        <clipPath id={`${id}-wedge`}>
          <path d="M25.4 42.9 H41.6 L56.0 54.2 L52.0 59.6 L25.4 64 Z" />
        </clipPath>
      </defs>
      <g mask={`url(#${id}-cut)`}>
        <rect width="64" height="64" fill="var(--logo-ink)" />
        <rect width="64" height="64" fill="var(--logo-signal)" clipPath={`url(#${id}-wedge)`} />
      </g>
    </svg>
  );
}

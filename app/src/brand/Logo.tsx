import mark from './fusion-mark.svg';
import './brand.css';
/** Kullanıcının F referansı: raster pikselleri korunur, SVG yalnız görünümü sınırlar. */
export interface LogoProps {
  size?: number;
  title?: string;
}
export function Logo({ size = 24, title }: LogoProps) {
  return <img className='fusion-logo' src={mark} alt={title ?? ''} width={size} height={size} />;
}

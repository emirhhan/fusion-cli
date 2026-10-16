import orbit from './reference-loading.png';
import './brand.css';
/** Kaynak sabit bir kare; hareket yalnız mevcut şeklin yavaş dönüşüdür. */
export function LoadingMark({ size = 42 }: { size?: number }) {
  return <span className='fusion-loading-mark' aria-hidden='true' style={{ width: size, height: size }}>
    <svg className='fusion-loading-mark__orbit' viewBox='18 20 88 84' width={size} height={size}>
      <image href={orbit} width='126' height='120' />
    </svg>
  </span>;
}

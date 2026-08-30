import "./FusionPixel.css";

/** Fusion işaretinden türeyen, yalnız boş ekranlarda kullanılan pixel karakter. */
export function FusionPixel({ size = 88 }: { size?: number }) {
  return (
    <svg
      aria-hidden="true"
      className="fusion-pixel"
      height={size}
      viewBox="0 0 88 88"
      width={size}
      xmlns="http://www.w3.org/2000/svg"
    >
      <g className="fusion-pixel__signal">
        <rect x="40" y="2" width="8" height="8" rx="2" />
        <rect x="42" y="10" width="4" height="8" />
      </g>
      <path className="fusion-pixel__shadow" d="M24 78h40v6H24z" />
      <path className="fusion-pixel__body" d="M24 56h40v22H24zM18 62h6v12h-6zM64 62h6v12h-6z" />
      <path className="fusion-pixel__head" d="M18 22h52v30H18zM24 16h40v6H24zM12 28h6v18h-6zM70 28h6v18h-6z" />
      <path className="fusion-pixel__face" d="M28 32h8v8h-8zM52 32h8v8h-8zM36 44h16v4H36z" />
      <path className="fusion-pixel__brand" d="M34 60h20v5H40v4h11v5H40v4h-6z" />
      <rect className="fusion-pixel__spark" x="8" y="18" width="5" height="5" />
      <rect className="fusion-pixel__spark" x="75" y="12" width="4" height="4" />
    </svg>
  );
}

/**
 * Mikrofon simgesi.
 *
 * Saf CSS ile kutu/kenarlık birleştirmek yerine gerçek bir yol kullanılır:
 * CSS hilesi her boyutta orantısını bozuyor ve kenarları kırılıyordu. Tek
 * `currentColor` ile çizilir, böylece düğmenin durumuna göre renk alır.
 */
export function MicIcon({ size = 26 }: { size?: number }) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height={size}
      stroke="currentColor"
      strokeLinecap="round"
      strokeWidth="1.9"
      viewBox="0 0 24 24"
      width={size}
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Kapsül gövde */}
      <rect x="9" y="2.5" width="6" height="11" rx="3" fill="currentColor" stroke="none" />
      {/* Yakalama yayı */}
      <path d="M5.5 11a6.5 6.5 0 0 0 13 0" />
      {/* Sap ve taban */}
      <path d="M12 17.5v3.2" />
      <path d="M8.6 20.7h6.8" />
    </svg>
  );
}

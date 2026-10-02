import type { ReactNode } from "react";

/**
 * Ekip üyesinin avatarı: renkli bir yuvarlak ve rolünü anlatan tek bir sembol.
 *
 * Neden çizim, neden yüz değil: avatar 28 px'de okunmalı. Yüz çizimi o boyutta
 * birbirine benzeyen lekelere dönüşüyordu; rol sembolü (pergel, köşeli parantez,
 * kalem ucu…) tek bakışta "kim çalışıyor"u söyler. Renk kişiliğin rengidir ve
 * tema token'larından gelir; koyu temada ayrı tonları vardır.
 */

const STROKE = {
  fill: "none",
  stroke: "currentColor",
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  strokeWidth: 1.8,
};

/** Avatar kimliği → 24×24 kutuda çizilen sembol. */
const SEMBOLLER: Record<string, ReactNode> = {
  mimar: (
    <g {...STROKE}>
      <circle cx="12" cy="6" r="1.6" />
      <path d="M11.2 7.5 7 18M12.8 7.5 17 18M8.6 14h6.8" />
    </g>
  ),
  kodcu: (
    <g {...STROKE}>
      <path d="M9 7 4.5 12 9 17M15 7l4.5 5-4.5 5M13 5.5l-2 13" />
    </g>
  ),
  tasarimci: (
    <g {...STROKE}>
      <path d="M12 4.5 17 11l-5 8.5L7 11z" />
      <path d="M12 4.5v7.5" />
      <circle cx="12" cy="13.2" r="1.2" />
    </g>
  ),
  testci: (
    <g {...STROKE}>
      <path d="M9.5 4.5h5M10.5 4.5v5l-4.2 7.4A1.6 1.6 0 0 0 7.7 19.5h8.6a1.6 1.6 0 0 0 1.4-2.6l-4.2-7.4v-5" />
      <path d="m9.6 14.6 1.7 1.7 3.2-3.4" />
    </g>
  ),
  arastirmaci: (
    <g {...STROKE}>
      <circle cx="10.5" cy="10.5" r="5" />
      <path d="m14.2 14.2 4.8 4.8" />
    </g>
  ),
  tarayici: (
    <g {...STROKE}>
      <circle cx="12" cy="12" r="7" />
      <path d="M5 12h14M12 5c2 2.2 2.8 4.5 2.8 7s-.8 4.8-2.8 7c-2-2.2-2.8-4.5-2.8-7S10 7.2 12 5z" />
    </g>
  ),
  gorselci: (
    <g {...STROKE}>
      <rect height="12" rx="2" width="14" x="5" y="6.5" />
      <path d="m5.5 16 4-4 3 3 2-2 4 4" />
      <circle cx="15.2" cy="10" r="1.2" />
    </g>
  ),
  yonetmen: (
    <g {...STROKE}>
      <rect height="9" rx="1.5" width="14" x="5" y="9.5" />
      <path d="m5 9.5 13-3.4M8.4 8.6l1.4 2.6M12.2 7.6l1.4 2.6" />
    </g>
  ),
  yardimci: (
    <g {...STROKE}>
      <path d="M12 4.5v3M12 16.5v3M4.5 12h3M16.5 12h3M7 7l2 2M15 15l2 2M17 7l-2 2M9 15l-2 2" />
    </g>
  ),
};

/** Bilinen renk adları; bilinmeyen ad gri görünür (uydurma renk üretilmez). */
const RENKLER = new Set([
  "mor", "mavi", "pembe", "yesil", "turuncu", "camgobegi", "sari", "kirmizi", "gri",
]);

export function ajanRengi(renk: string): string {
  return RENKLER.has(renk) ? renk : "gri";
}

export interface AgentAvatarProps {
  avatar: string;
  renk: string;
  /** Erişilebilir ad: "Arayüz Tasarımcısı". */
  ad: string;
  boyut?: number;
  /** Ajan çalışıyor mu? Çalışırken avatarın çevresinde ince bir halka döner. */
  calisiyor?: boolean;
}

export function AgentAvatar({ avatar, renk, ad, boyut = 28, calisiyor = false }: AgentAvatarProps) {
  const sembol = SEMBOLLER[avatar] ?? SEMBOLLER.yardimci;
  return (
    <span
      aria-label={ad}
      className="agent-avatar"
      data-renk={ajanRengi(renk)}
      data-running={calisiyor ? "true" : undefined}
      role="img"
      style={{ width: boyut, height: boyut }}
    >
      <svg aria-hidden="true" height={boyut * 0.64} viewBox="0 0 24 24" width={boyut * 0.64}>
        {sembol}
      </svg>
    </span>
  );
}

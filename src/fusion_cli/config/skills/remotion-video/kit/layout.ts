// Sınırlar render pikseli cinsinden; dekoratif zemin/ışık öğeleri ölçülmez.
export type ContentRect = {label: string; left: number; top: number; right: number; bottom: number};
export const layoutPolicy = {safeMargin: 120, overlapTolerance: 4, minOpacity: 0.5};

export const inspectLayout = (
  content: ContentRect[], viewport: {width: number; height: number},
  margin = layoutPolicy.safeMargin,
): string[] => {
  if (!content.length) return ["Okunabilir içerik yok; yalnız zemin/dekor ya da soluk yazı var."];
  const findings: string[] = [];
  for (const item of content) {
    if (item.left < margin || item.top < margin || item.right > viewport.width - margin || item.bottom > viewport.height - margin) {
      findings.push(`${item.label}: güvenli alan dışına taşıyor (${Math.round(item.left)},${Math.round(item.top)}–${Math.round(item.right)},${Math.round(item.bottom)}).`);
    }
  }
  content.forEach((first, index) => {
    for (const second of content.slice(index + 1)) {
      const width = Math.min(first.right, second.right) - Math.max(first.left, second.left);
      const height = Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top);
      if (width > layoutPolicy.overlapTolerance && height > layoutPolicy.overlapTolerance) {
        findings.push(`${first.label} / ${second.label}: üst üste biniyor (${Math.round(width)}×${Math.round(height)} px).`);
      }
    }
  });
  return findings;
};

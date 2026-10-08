// Sınırlar render pikseli cinsinden; dekoratif zemin/ışık öğeleri ölçülmez.
export type ContentRect = {label: string; left: number; top: number; right: number; bottom: number};
export const layoutPolicy = {safeMargin: 120, overlapTolerance: 4, minOpacity: 0.5};

export type LayoutFinding = {family: "empty" | "overflow" | "overlap"; message: string};

export const inspectLayoutEvidence = (
  content: ContentRect[], viewport: {width: number; height: number},
  margin = layoutPolicy.safeMargin,
): LayoutFinding[] => {
  if (!content.length) return [{family: "empty", message: "Okunabilir içerik yok; yalnız zemin/dekor ya da soluk yazı var."}];
  const findings: LayoutFinding[] = [];
  for (const item of content) {
    if (item.left < margin || item.top < margin || item.right > viewport.width - margin || item.bottom > viewport.height - margin) {
      findings.push({family: "overflow", message: `${item.label}: güvenli alan dışına taşıyor (${Math.round(item.left)},${Math.round(item.top)}–${Math.round(item.right)},${Math.round(item.bottom)}).`});
    }
  }
  content.forEach((first, index) => {
    for (const second of content.slice(index + 1)) {
      const width = Math.min(first.right, second.right) - Math.max(first.left, second.left);
      const height = Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top);
      if (width > layoutPolicy.overlapTolerance && height > layoutPolicy.overlapTolerance) {
        findings.push({family: "overlap", message: `${first.label} / ${second.label}: üst üste biniyor (${Math.round(width)}×${Math.round(height)} px).`});
      }
    }
  });
  return findings;
};

export const inspectLayout = (content: ContentRect[], viewport: {width: number; height: number}, margin = layoutPolicy.safeMargin): string[] =>
  inspectLayoutEvidence(content, viewport, margin).map(finding => finding.message);

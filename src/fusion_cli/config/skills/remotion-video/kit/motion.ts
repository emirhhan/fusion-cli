// Kamera/derinlik varsayılanları ile güvenli sahne bütçesi aynı kaynaktan gelir.
export const motionDefaults = {
  cameraFrom: 1, cameraTo: 1.05, cameraDrift: 20,
  verticalDriftRatio: 0.4, parallaxX: 28, parallaxY: 10,
};

export const featureSceneInset = (size: number, margin: number, vertical = false): number => {
  const scale = Math.max(motionDefaults.cameraFrom, motionDefaults.cameraTo);
  const drift = motionDefaults.cameraDrift * (vertical ? motionDefaults.verticalDriftRatio : 1);
  const parallax = vertical ? motionDefaults.parallaxY : motionDefaults.parallaxX;
  // Ortadan ölçekleme ve ölçek içindeki iki yönde en kötü kaymayı birlikte ayır.
  return Math.ceil((margin + (scale - 1) * size / 2 + scale * (drift + parallax)) / scale);
};

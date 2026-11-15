/** Beklenen işlem hatası: istemciye 200 + { error } olarak döner, araç kartı gösterir. */
export class OperationError extends Error {}

/** Durum çakışması (kontrol insanda, anlık görüntü eski vb.): HTTP 409. */
export class ConflictError extends Error {}

import { errorMessage } from "../protocol/result";
export type StorageAccess = () => Pick<Storage, "getItem" | "setItem" | "removeItem">;
export type StorageResult<T> = { ok: true; value: T } | { ok: false; message: string };
/** Nesneyi değil getter'ı alır: SecurityError erişimin kendisinde oluşabilir. */
export function readStorage(access: () => Pick<Storage, "getItem">, key: string): StorageResult<string | null> {
  try { return { ok: true, value: access().getItem(key) }; }
  catch (reason) { return { ok: false, message: errorMessage(reason) }; }
}
export function writeStorage(access: () => Pick<Storage, "setItem">, key: string, value: string): StorageResult<void> {
  try { access().setItem(key, value); return { ok: true, value: undefined }; }
  catch (reason) { return { ok: false, message: errorMessage(reason) }; }
}
export function removeStorage(access: () => Pick<Storage, "removeItem">, key: string): StorageResult<void> {
  try { access().removeItem(key); return { ok: true, value: undefined }; }
  catch (reason) { return { ok: false, message: errorMessage(reason) }; }
}

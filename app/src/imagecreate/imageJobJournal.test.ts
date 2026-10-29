import { beforeEach, expect, it } from "vitest";
import { ImageJobJournal } from "./imageJobJournal";

beforeEach(() => localStorage.clear());
it("iş kimliğini üretimden önce kalıcı tutar ve yeniden açılışta okur", () => {
  const journal = new ImageJobJournal(localStorage, "root/conversation");
  journal.add("job-1");
  expect(new ImageJobJournal(localStorage, "root/conversation").read()).toEqual(["job-1"]);
  expect(new ImageJobJournal(localStorage, "other/conversation").read()).toEqual([]);
  journal.remove("job-1");
  expect(journal.read()).toEqual([]);
});
it("paralel sahiplerin eklediği kimlikleri kaybetmez", () => {
  const first = new ImageJobJournal(localStorage, "scope");
  const second = new ImageJobJournal(localStorage, "scope");
  first.add("job-a"); second.add("job-b");
  first.remove("job-a");
  expect(second.read()).toEqual(["job-b"]);
});
it("bozuk veya gelecek kayıtları sessizce atlayıp yeni üretime izin vermez", () => {
  const journal = new ImageJobJournal(localStorage, "scope");
  journal.add("job-a");
  const key = localStorage.key(0)!;
  localStorage.setItem(key, JSON.stringify({ version: 2, jobId: "job-a" }));
  expect(() => journal.read()).toThrow(/doğrulanamadı/);
});
it("tek bozuk kaydı karantinaya alır, sağlam işleri açar ve yeni üretime izin verir", () => {
  const journal = new ImageJobJournal(localStorage, "scope");
  journal.add("job-a"); journal.add("job-b");
  const keyA = [...Array(localStorage.length).keys()].map((i) => localStorage.key(i)!).find((k) => k.endsWith("job-a"))!;
  localStorage.setItem(keyA, "{bozuk");
  expect(journal.read()).toEqual(["job-b"]);
  expect(localStorage.getItem(keyA)).toBeNull();
  const quarantined = [...Array(localStorage.length).keys()].map((i) => localStorage.key(i)!).filter((k) => k.startsWith("fusion:image-jobs-quarantine:"));
  expect(quarantined).toHaveLength(1);
  expect(localStorage.getItem(quarantined[0])).toBe("{bozuk");
  journal.add("job-c");
  expect(journal.read()).toEqual(["job-b", "job-c"]);
});
it("kimliği anahtarıyla uyuşmayan kayıt da karantinaya alınır", () => {
  const journal = new ImageJobJournal(localStorage, "scope");
  journal.add("job-a");
  localStorage.setItem(localStorage.key(0)!, JSON.stringify({ version: 1, jobId: "job-z" }));
  expect(journal.read()).toEqual([]);
});
it("kayıt yazılamıyorsa üretim için kimlik oluşturulmuş sayılmaz", () => {
  const storage = { length: 0, key: () => null, getItem: () => null, setItem: () => { throw new Error("quota"); }, removeItem: () => {} };
  expect(() => new ImageJobJournal(storage, "scope").add("job-a")).toThrow(/kaydedilemedi/);
});
it("kimlik ve kapsam sınırlarını doğrular", () => {
  expect(() => new ImageJobJournal(localStorage, "")).toThrow();
  expect(() => new ImageJobJournal(localStorage, "scope").add("../other")).toThrow();
});

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
it("kayıt yazılamıyorsa üretim için kimlik oluşturulmuş sayılmaz", () => {
  const storage = { length: 0, key: () => null, getItem: () => null, setItem: () => { throw new Error("quota"); }, removeItem: () => {} };
  expect(() => new ImageJobJournal(storage, "scope").add("job-a")).toThrow(/kaydedilemedi/);
});
it("kimlik ve kapsam sınırlarını doğrular", () => {
  expect(() => new ImageJobJournal(localStorage, "")).toThrow();
  expect(() => new ImageJobJournal(localStorage, "scope").add("../other")).toThrow();
});

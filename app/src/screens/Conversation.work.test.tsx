import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Conversation, type Mesaj } from "./Conversation";
afterEach(cleanup);
const messages: Mesaj[] = [
  { id: "u", rol: "kullanici", metin: "Projeyi yap" },
  { id: "n1", rol: "asistan", metin: "Dosyaları okuyorum", ara: true },
  { id: "e", rol: "olay", metin: "okundu", adimlar: [{ metin: "main.py okundu", arac: "read_file", durum: "ok" }] },
  { id: "n2", rol: "asistan", metin: "Testleri çalıştırıyorum", ara: true },
];
it("biten geçmiş son cevabın üzerinde kapalıdır", () => {
 const {container}=render(<Conversation running={false} mesajlar={[...messages.map(message=>message.id==="e"?{...message,baslangicZamani:1000}:message),{id:"a",rol:"asistan",metin:"Sonuç hazır",bitisZamani:924000}]} />);
 const history=container.querySelector<HTMLDetailsElement>(".conversation__work-details")!;
 expect(history).toBeTruthy(); expect(history.open).toBe(false);
 expect(screen.getByText("Sonuç hazır").closest("details")).toBeNull();
 expect(screen.getByText("15d 23sn çalıştı")).toBeTruthy();
 fireEvent.click(history.querySelector("summary")!); expect(history.open).toBe(true);
});
it("cevapsız durdurulan geçmiş açık kalır",()=>{
 const {container}=render(<Conversation running={false} mesajlar={messages}/>);
 expect(container.querySelector(".conversation__work-details")).toBeNull();
 expect(screen.getByText("main.py okundu").closest(".activity__summary")).toBeNull();
});
it("ardışık eş anlatımlar sunumda birleşir",()=>{
 render(<Conversation running mesajlar={[messages[0],messages[1],{...messages[1],id:"duplicate"},...messages.slice(2)]}/>);
 expect(screen.getAllByText("Dosyaları okuyorum")).toHaveLength(1);
});
it("görev listesi sınırında yalnız gerçek son araç canlı kalır", () => {
  const { container } = render(<Conversation running mesajlar={[
    ...messages.slice(0, 3),
    { id: "tasks", rol: "gorevler", metin: "Görevler", gorevler: [] },
    { id: "new-event", rol: "olay", metin: "test", adimlar: [{ metin: "Test çalışıyor", arac: "run_shell", basladi: true }] },
  ]} />);
  expect(container.querySelectorAll('.activity[data-state="running"]')).toHaveLength(1);
});
it("hata ana akışta raporlanabilir kalır", () => {
  render(<Conversation running={false} onHataBildir={() => {}} mesajlar={[
    ...messages, { id: "error", rol: "asistan", metin: "Hata: Bağlantı kurulamadı", ara: true, hata: true },
  ]} />);
  expect(screen.getByText("Hata: Bağlantı kurulamadı").closest("details")).toBeNull();
  expect(screen.getByRole("button", { name: "Hatayı bildir" })).toBeTruthy();
});
it("alt ajan bitişini referanstaki gibi küçük ikonlu işlem satırında gösterir",()=>{
 const {container}=render(<Conversation running={false} mesajlar={[{id:'team',rol:'ekip',metin:'Ekip',ajanlar:[{id:'review',persona:'yardimci',unvan:'Review resume',avatar:'yardimci',renk:'mor',gorev:'İncele',durum:'bitti',adimlar:[],baslangic:1}]}]} />);
 expect(screen.getByText('Review resume çalışmayı bitirdi').closest('summary')?.querySelector('svg')).toBeTruthy();
 expect(container.querySelector('.team-cards')).toBeNull();
});

it("geçmiş turların son cevapları ve özgün devam indisi korunur", () => {
 const onContinue=vi.fn();
 const {container}=render(<Conversation running={false} onContinueInNewChat={onContinue} mesajlar={[
 ...messages,{id:"final1",rol:"asistan",metin:"İlk sonuç"},
 {id:"u2",rol:"kullanici",metin:"Devam"},
 {id:"n3",rol:"asistan",ara:true,metin:"İkinci işlem"},
 {id:"final2",rol:"asistan",metin:"İkinci sonuç"},
 ]}/>);
 expect(container.querySelectorAll(".conversation__work-details")).toHaveLength(2);
 expect(screen.getAllByText("Çalışma geçmişi")).toHaveLength(2);
 const answer=screen.getByText("İkinci sonuç").closest("article")!;
 fireEvent.click(answer.querySelector('button[aria-label="Yeni sohbette devam et"]')!);
 expect(onContinue).toHaveBeenCalledWith(7);
});
it("başarısız araç kanıtı kompakt geçmişte açılabilir kalır",()=>{
 render(<Conversation running={false} mesajlar={[{id:"failed",rol:"olay",metin:"Hata",adimlar:[
 {metin:"Komut başarısız",arac:"run_shell",durum:"failed",komut:"pytest",cikti:"Başarısız test"},
 {metin:"Tur bitti",sonuc:"failed"},
 ]}]}/>);
 const step=screen.getByText("Komut başarısız").closest("details")!;
 fireEvent.click(step.querySelector("summary")!);expect(step.open).toBe(true);
 expect(screen.getByText("Başarısız test")).toBeTruthy();
});

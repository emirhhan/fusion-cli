import React from "react";
import { createRoot } from "react-dom/client";
import { Conversation, type Mesaj } from "../src/screens/Conversation";
import "../src/theme/tokens.css";
import "../src/brand/brand.css";
import "../src/App.css";
const params = new URLSearchParams(location.search);
document.documentElement.dataset.theme = params.get("theme") ?? "dark";
const running = params.get("running") === "1";
const paths = ["tests/test_turn_journal.py", "src/fusion_cli/appserver/session.py", "src/fusion_cli/core/turn_resume.py", "app/src/screens/Conversation.tsx", "app/src/screens/ActivityLine.tsx", "app/src/screens/ChangeSummary.tsx", "app/src/sessions/history.ts", "tests/test_appserver_history_view.py", "src/fusion_cli/memory/turn_journal.py", "app/src/theme/tokens.css"];
const step = (path: string) => ({ metin: "Dosya düzenlendi", arac: "edit_file", yol: path, durum: "ok" as const, diff: `--- a/${path}\n+++ b/${path}\n@@ -1 +1,2 @@\n-onceki\n+guncel\n+dogrulandi\n` });
const messages: Mesaj[] = [
 {id:"u",rol:"kullanici",metin:"Kaldığın yerden devam et."},
 {id:"n1",rol:"asistan",ara:true,metin:"Kaynak dosyaların tamamını ilk koşunun kayıtlarıyla karşılaştırdım; hepsi ilk durdurduğun andaki içerikle eşleşiyor.\n\nDüzeltmenin kapsamlı testleri ve kurulu Fusion için yeni çalışma zamanı paketi hazırlanıyor."},
 {id:"e1",baslangicZamani:1000,rol:"olay",metin:"İşlemler",adimlar:[step(paths[0]),{metin:"Komut çalıştırıldı",arac:"run_shell",durum:"ok",ayrinti:"pytest: 27 passed"}]},
 {id:"team",rol:"ekip",metin:"İnceleme",ajanlar:[{id:"review",persona:"yardimci",unvan:"Review resume",avatar:"yardimci",renk:"mor",gorev:"Devam davranışını incele",durum:"bitti",adimlar:[],baslangic:1}]},
 {id:"n2",rol:"asistan",ara:true,metin:"Devam davranışıyla ilgili 131 test geçti; Ruff ve tip denetimi de temiz.\n\nŞimdi yeni paketin çalıştığını doğrulayıp Fusion’ı güncelleyeceğim."},
 {id:"e2",bitisZamani:running?undefined:924000,rol:"olay",metin:"İşlemler",adimlar:paths.slice(1).map(step)},
 {id:"n3",rol:"asistan",ara:true,metin:"Yeni paket ve paketli çalışma zamanı kontrolü geçti. Güncellemeyi uygulamak için Fusion’ı kısa süre kapatıp yeniden açacağım."},
 ...(running?[]:[{id:"final",rol:"asistan" as const,metin:"Düzelttim ve **Fusion’ı kurup açtım.**\n\n- Durdurulan turun araç geçmişi korunuyor.\n- Sohbet ilk durdurma noktasına döndü.\n- İlgili testler ve tip denetimi geçti.\n\n**Şimdi aynı Fusion sohbetine ‘Devam et’ yazabilirsin.**"}]),
];
createRoot(document.getElementById("root")!).render(<main style={{display:"flex",flexDirection:"column",height:"100dvh",containerType:"inline-size",containerName:"conversation-workspace",color:"var(--text-primary)"}}><Conversation mesajlar={messages} running={running} onOpenFile={path=>{document.documentElement.dataset.openedFile=path;}} /></main>);

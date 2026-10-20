import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import '../src/theme/tokens.css';
import { applyTheme } from '../src/theme/theme';
import { VoiceMode } from '../src/voice/VoiceMode';
import type { VoiceAsk } from '../src/voice/bridge';
const params=new URLSearchParams(location.search);
applyTheme(params.get('theme')==='light'?'light':'dark');
const question:VoiceAsk={sessionId:'fixture',questionId:'question-1',acik:true,metin:'İki dosyadaki düzenlemeler uygulansın mı?\n\nBu test sorusunun tamamıdır. Dosyalar: app.ts ve theme.css. Dışarıya veri gönderilmez.\n'+Array(12).fill('Uzun sorunun tüm satırları kaydırılarak okunabilir.').join('\n'),secenekler:[{deger:'approve_once',etiket:'Bu kez izin ver'},{deger:'deny',etiket:'Reddet'}]};
type Controls={newQuestion:()=>void;answers:string[]};
declare global { interface Window { petReview?:Controls } }
function Review(){
 const [wide,setWide]=useState(false);const [ask,setAsk]=useState<VoiceAsk|null>(params.get('question')==='0'?null:question);const [answers]=useState<string[]>([]);
 window.petReview={newQuestion:()=>setAsk({...question,questionId:'question-2',metin:'Yeni soruyu oku.\n\nYeni tam metin.'}),answers};
 return <VoiceMode ask={ask} onAnswer={answer=>{answers.push(answer)}} answerPending={params.get('pending')==='1'} onClose={()=>{}} onMinimize={()=>{}} onWideChange={setWide} onPrefsChange={()=>{}} onTopChange={()=>{}} listening={false} state={ask?'approval':'thinking'} wide={wide}/>;
}
createRoot(document.getElementById('root')!).render(<Review/>);

// Gerçek DOM çizimi geniş izinleri ve seçenek kapsamını kaybetmez.
import assert from 'node:assert/strict';
import {renderAsk, renderSites} from '../../chrome-extension/panelView.js';
// Yalnız kullanılan DOM sözleşmesi sahte; çizim fonksiyonları gerçek modülden gelir.
class Element {
  constructor(tag) {this.tag=tag;this.children=[];this.dataset={};this.listeners={};this.text='';}
  set textContent(value) {this.text=String(value);this.children=[];}
  get textContent() {return this.text+this.children.map((child)=>typeof child==='string'?child:child.textContent).join('');}
  append(...children) {this.children.push(...children);}
  replaceChildren(...children) {this.children=[...children];}
  addEventListener(name,listener) {this.listeners[name]=listener;}
  click() {this.listeners.click?.();}
  focus() {}
}
const elements=new Map(['ask','sites','empty'].map((id)=>[id,new Element('div')]));
const find=(node,tag)=>node.tag===tag?node:node.children.map((child)=>typeof child==='string'?null:find(child,tag)).find(Boolean);
const document={getElementById:(id)=>elements.get(id),createElement:(tag)=>new Element(tag),querySelector:(tag)=>[...elements.values()].map((node)=>find(node,tag)).find(Boolean)};
globalThis.document=document;
let removed;
renderSites(document.getElementById('sites'), document.getElementById('empty'), ['<all_urls>', 'https://*/*'], (origin) => {removed=origin;});
assert.match(document.getElementById('sites').textContent, /Tüm siteler/);
document.querySelector('button').click();
assert.equal(removed,'<all_urls>');
renderAsk(document.getElementById('ask'), {id:'q',veri:{tur:'onay',secenekler:[{deger:'session',etiket:'Bu oturumda izin ver',aciklama:'Yalnız work.test; uygulama kapanınca sona erer.'}]}},()=>{});
assert.match(document.getElementById('ask').textContent,/uygulama kapanınca sona erer/);
console.log('chrome-permission-view ✓');

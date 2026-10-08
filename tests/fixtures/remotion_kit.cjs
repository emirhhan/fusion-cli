// Remotion'un kare bağlamını sabitle; gerçek React bileşenlerini ve geometriyi çalıştır.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const assert = require('node:assert/strict');
const root = process.argv[2];
const ts = require(path.join(root, 'app/node_modules/typescript'));
const React = require(path.join(root, 'app/node_modules/react'));
const {renderToStaticMarkup} = require(path.join(root, 'app/node_modules/react-dom/server'));
const kit = process.argv[4] || path.join(root, 'src/fusion_cli/config/skills/remotion-video/kit');
let frame = 90;
const remotion = {
  useCurrentFrame: () => frame,
  useVideoConfig: () => ({width: 1920, height: 1080, fps: 30, durationInFrames: 120}),
  spring: () => 1,
  interpolate: (v, [a,b], [c,d]) => c + Math.max(0, Math.min(1, (v-a)/(b-a))) * (d-c),
  AbsoluteFill: ({children, style}) => React.createElement('div', {style: {position: 'absolute', inset: 0, display: 'flex', ...style}}, children),
};
function load(name) {
  const file = path.join(kit, name + '.tsx');
  const source = fs.existsSync(file) ? file : path.join(kit, name + '.ts');
  const mod = new Module(source);
  mod.filename = source;
  mod.require = (id) => id === 'react' ? React : id === 'remotion' ? remotion : id.startsWith('./') ? load(id.slice(2)) : require(id);
  mod._compile(ts.transpileModule(fs.readFileSync(source, 'utf8'), {compilerOptions: {jsx: ts.JsxEmit.React, module: ts.ModuleKind.CommonJS, esModuleInterop: true}}).outputText, source);
  return mod.exports;
}
if (process.argv[3] === 'timeline') {
  const esbuild = require(path.join(root, 'app/node_modules/esbuild'));
  const result = esbuild.buildSync({
    stdin: {contents: `import React from 'react'; import {createRoot} from 'react-dom/client'; import {FusionTimeline,LayoutAudit,FeatureScene} from '${kit}/index';
      const mode = new URLSearchParams(location.search).get('mode');
      globalThis.__fusionTestFrame = mode==='boundary-before'?59:mode==='boundary-after'?60:0;
      globalThis.__fusionTestSpring=0;
      if(mode==='runtime'||mode==='runtime-failure')globalThis.__fusionTestSession='new-session';
      if(mode==='offscreen-short'){globalThis.__fusionTestDuration=30;globalThis.__fusionTestFrame=29;}
      const title=React.createElement('div',{'data-fusion-content':'Custom',style:{position:'absolute',left:mode==='sliver'?1918:mode==='partial'?1800:mode.startsWith('offscreen')?5000:200,top:200,width:500,height:100}},'Custom');
      const Custom=()=>['blank','runtime-failure'].includes(mode)?null:title;
      const props={title:'Fusion',subtitle:'Üç kısa özellik',cards:[{title:'Hız',body:mode==='capacity'?'Uzun metin '.repeat(200):'Akıcı'},{title:'Güven',body:'Sağlam'}]};
      let scenes=[{id:'first',kind:'feature',duration:60,props},{id:'second',kind:'custom',duration:60,component:Custom}];
      if(['blank','sliver','partial','runtime-failure'].includes(mode)||mode.startsWith('offscreen'))scenes=[{id:'blank',kind:'custom',duration:mode==='offscreen-short'?30:120,component:Custom}];
      if(mode==='duration')scenes[0].duration=59;
      if(mode==='duplicate')scenes[1].id='first';
      if(mode==='zero')scenes[0].duration=0;
      let element=React.createElement(FusionTimeline,{scenes});
      if(mode==='overlap')element=React.createElement(LayoutAudit,{scope:'composition'},['a','b'].map(id=>React.createElement('div',{'data-fusion-scene':id,key:id},title)));
      const reactRoot=createRoot(document.getElementById('root'));reactRoot.render(element);
      globalThis.__rerenderFrame=frame=>{globalThis.__fusionTestFrame=frame;reactRoot.render(React.createElement(FusionTimeline,{scenes:[...scenes]}));};`, resolveDir:path.join(root,'app'),loader:'tsx'},
    bundle:true,write:false,format:'iife',nodePaths:[path.join(root,'app/node_modules')],
    alias:{remotion:path.join(__dirname,'remotion_context.cjs')},
  });
  process.stdout.write('<html><body style="margin:0"><div data-fusion-canvas style="position:relative;width:1920px;height:1080px"><div id="root" style="position:relative;width:1920px;height:1080px"></div></div><script>'+result.outputFiles[0].text+'</script></body></html>');
  return;
}
if (process.argv[3] === 'feature') {
  const esbuild = require(path.join(root, 'app/node_modules/esbuild'));
  const result = esbuild.buildSync({
    stdin: {contents: `import React from 'react'; import {createRoot} from 'react-dom/client'; import {FeatureScene} from '${kit}/index';
      const mode = new URLSearchParams(location.search).get('mode');
      globalThis.__fusionTestFrame = ['oversize','longword','near-entrance'].includes(mode) ? 0 : 60;
      if(mode.startsWith('near-')) {globalThis.__fusionTestSpring=mode==='near-entrance'?0:1; const style=document.createElement('style');style.textContent='[data-fusion-feature-body]{height:385px}';document.head.appendChild(style);}
      if(mode==='font-delayed') Object.defineProperty(document.fonts,'ready',{value:new Promise(resolve=>{globalThis.__releaseFonts=resolve;})});
      const cards = mode==='too-many' ? Array.from({length:4},(_,i)=>({title:'Kart '+i,body:'Açıklama'})) : [
        {title:'Hız',body:mode==='oversize'?'Uzun açıklama '.repeat(90):mode==='longword'?'W'.repeat(400):'Kısa açıklama'},
        {title:'Güven',body:'Net ölçüm'}, {title:'Akış',body:'Somut sonuç'}];
      createRoot(document.getElementById('root')).render(React.createElement(FeatureScene,{title:'Fusion özellikleri',subtitle:'Birlikte çalışan üç yetenek',cards}));`, resolveDir: path.join(root,'app'), loader:'tsx'},
    bundle:true, write:false, format:'iife', nodePaths:[path.join(root,'app/node_modules')],
    alias: {remotion:path.join(__dirname,'remotion_context.cjs')},
  });
  process.stdout.write('<html><body style="margin:0"><div data-fusion-canvas style="position:relative;width:1920px;height:1080px"><div id="root" style="position:relative;width:1920px;height:1080px"></div></div><script>'+result.outputFiles[0].text+'</script></body></html>');
  return;
}
if (process.argv[3] === 'audit') {
  const esbuild = require(path.join(root, 'app/node_modules/esbuild'));
  const result = esbuild.buildSync({
    stdin: {contents: `import React from 'react'; import {createRoot} from 'react-dom/client'; import {LayoutAudit} from '${kit}/LayoutAudit';
      const mode = new URLSearchParams(location.search).get('mode');
      const a = React.createElement('div', {key:'a', 'data-fusion-content': 'Başlık', style:{position:'absolute',left:mode==='overflow'?110:160,top:160,width:500,height:100}}, 'Başlık');
      const b = React.createElement('div', {key:'b', 'data-fusion-content': 'Alt yazı', style:{position:'absolute',left:160,top:['overlap','nested','delayed'].includes(mode)?180:300,width:500,height:100}}, 'Alt yazı');
      let content = ['empty','dim'].includes(mode) ? (mode==='dim'?React.createElement('div',{'data-fusion-content':'Soluk',style:{opacity:.15}},'Fusion'):null) : [a,b];
      if(mode==='nested') content=React.createElement('div',{'data-fusion-content':'Grup'},content);
      let audit=React.createElement(LayoutAudit,null,content);
      if(mode==='transform') audit=React.createElement('div',{style:{position:'absolute',inset:0,transform:'translateX(-100px)'}},audit);
      if(mode==='delayed'){document.getElementById('root').style.display='none';setTimeout(()=>document.getElementById('root').style.display='block',150);}
      createRoot(document.getElementById('root')).render(audit);`, resolveDir: path.join(root,'app'), loader:'tsx'},
    bundle:true, write:false, format:'iife', nodePaths:[path.join(root,'app/node_modules')],
    alias: {remotion:path.join(__dirname,'remotion_context.cjs')},
  });
  process.stdout.write('<html><body style="margin:0"><div id="remotion-canvas" style="position:relative;width:1920px;height:1080px"><div id="root" style="position:relative;width:1920px;height:1080px"></div></div><script>'+result.outputFiles[0].text+'</script></body></html>');
  return;
}
const {Parallax} = load('CameraPush');
const {FeatureCard} = load('FeatureCard');
if (process.argv[3] === 'feature-geometry') {
  const {featureSceneInset, motionDefaults} = load('motion');
  const {inspectLayout} = load('layout');
  const width=1920,height=1080,margin=120;
  const horizontal=featureSceneInset(width,margin),vertical=featureSceneInset(height,margin,true);
  for(const scale of [motionDefaults.cameraFrom,motionDefaults.cameraTo]) {
    for(const direction of [-1,1]) {
      const dx=direction*(motionDefaults.cameraDrift+motionDefaults.parallaxX)*scale;
      const dy=direction*(motionDefaults.cameraDrift*motionDefaults.verticalDriftRatio+motionDefaults.parallaxY)*scale;
      const rect={label:'Özellik sahnesi',left:width/2+(horizontal-width/2)*scale+dx,right:width/2+(width-horizontal-width/2)*scale+dx,top:height/2+(vertical-height/2)*scale+dy,bottom:height/2+(height-vertical-height/2)*scale+dy};
      assert.deepEqual(inspectLayout([rect],{width,height},margin),[]);
    }
  }
  process.stdout.write('özellik geometrisi geçti');
  return;
}
if (process.argv[3] === 'geometry') {
  const {inspectLayoutEvidence}=load('layout');
  assert.equal(inspectLayoutEvidence([], {width:1920,height:1080})[0].family,'empty');
  assert.equal(inspectLayoutEvidence([{label:'A',left:0,top:0,right:300,bottom:300}], {width:1920,height:1080})[0].family,'overflow');
  assert.equal(inspectLayoutEvidence([{label:'A',left:200,top:200,right:500,bottom:500},{label:'B',left:250,top:250,right:550,bottom:550}], {width:1920,height:1080})[0].family,'overlap');
  const {inspectLayout} = load('layout');
  const viewport = {width: 1920, height: 1080};
  const rect = (label, left, top, width, height) => ({label, left, top, right: left+width, bottom: top+height});
  assert.deepEqual(inspectLayout([rect('Başlık',120,120,500,100),rect('Kart',120,260,580,300)],viewport,120), []);
  assert.match(inspectLayout([rect('Taşma',110,120,500,100)],viewport,120).join(' '), /Taşma/);
  assert.match(inspectLayout([rect('Başlık',120,120,500,100),rect('Alt yazı',120,180,500,100)],viewport,120).join(' '), /üst üste/);
  assert.match(inspectLayout([],viewport,120).join(' '), /içerik yok/);
  process.stdout.write('geometri geçti');
} else {
  const tree = React.createElement('div', {style: {width: 1680, display: 'flex', flexDirection: 'column'}},
    React.createElement(Parallax, {depth: 0}, React.createElement('div', {id: 'title', style: {height: 100}}, 'Başlık')),
    React.createElement(Parallax, {depth: 0}, React.createElement('div', {id: 'subtitle', style: {height: 100}}, 'Alt yazı')),
    React.createElement(FeatureCard, {title: 'Kart', body: 'Açıklama', width: 580}));
  process.stdout.write(renderToStaticMarkup(tree));
}

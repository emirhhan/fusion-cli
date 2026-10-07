// Remotion'un kare bağlamını sabitle; gerçek React bileşenlerini ve geometriyi çalıştır.
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const assert = require('node:assert/strict');
const root = process.argv[2];
const ts = require(path.join(root, 'app/node_modules/typescript'));
const React = require(path.join(root, 'app/node_modules/react'));
const {renderToStaticMarkup} = require(path.join(root, 'app/node_modules/react-dom/server'));
const kit = path.join(root, 'src/fusion_cli/config/skills/remotion-video/kit');
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
if (process.argv[3] === 'geometry') {
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

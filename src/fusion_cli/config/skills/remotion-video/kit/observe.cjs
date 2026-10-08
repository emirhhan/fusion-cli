// Kaynak/model beyanı değil: renderer'ın tarayıcı konsolundaki oturum kaydı.
const path = require('node:path');
const {createRequire} = require('node:module');
const RUNTIME_PREFIX = 'FUSION_RUNTIME_V1:';
// Kurulu renderer sürümünün yerel tarayıcısı yoksa indirme/kurulum yapma.
function installedBrowser(localRequire) {
  const directory = path.dirname(localRequire.resolve('@remotion/renderer'));
  const fetcher = localRequire(path.join(directory, 'browser/BrowserFetcher.js'));
  const chromeMode = 'headless-shell';
  const revision = fetcher.getRevisionInfo(chromeMode);
  const expected = fetcher.getExpectedVersion({version:null, chromeMode, platform:fetcher.getPlatform()});
  if(!revision.local || !require('node:fs').existsSync(revision.executablePath) || fetcher.readVersionFile(chromeMode) !== expected) {
    throw new Error('Uyumlu yerel Chromium kurulu değil; gözlem doğrulanamadı, indirme yapılmadı.');
  }
  return revision.executablePath;
}
async function main() {
  const request = JSON.parse(process.argv[2]);
  let stage='dependencies';
  const messages=[];
  const limit=request.diagnosticLimit;
  const bounded=value=>String(value).slice(0,limit);
  const emit=value=>process.stdout.write('FUSION_OBSERVE_V1:'+JSON.stringify({session:request.session,composition:request.composition,frame:request.frame,stage,...value})+'\n');
  const progress=(message='')=>{
    const header={session:request.session,composition:request.composition,frame:request.frame,stage};
    const prefix='FUSION_PROGRESS_V1:';
    let text=bounded(message);
    let line=prefix+JSON.stringify({...header,message:text})+'\n';
    while(Buffer.byteLength(line,'utf8')>limit&&text.length) {
      text=text.slice(0,Math.floor(text.length/2));
      line=prefix+JSON.stringify({...header,message:text})+'\n';
    }
    if(Buffer.byteLength(line,'utf8')<=limit)process.stderr.write(line);
  };
  progress();
  // Renderer Chromium'u ayrı process group ile açar; yalnız kendi spawn sınırımızı kaydet.
  const childProcess = require('node:child_process');
  const spawn = childProcess.spawn;
  childProcess.spawn = function(command, args, options) {
    const owned = spawn.call(this, command, args, options);
    if(options?.detached && owned.pid && request.cleanupFile) {
      require('node:fs').appendFileSync(request.cleanupFile, String(owned.pid)+'\n');
    }
    return owned;
  };
  const localRequire = createRequire(path.join(process.cwd(), 'package.json'));
  let renderer, bundler;
  try {renderer=localRequire('@remotion/renderer');bundler=localRequire('@remotion/bundler');}
  catch {emit({rendered:false,error:'Mevcut renderer/bundler kurulu değil.'});process.exitCode=1;return;}
  let record = null, browser = null;
  const closeBrowser = async () => {if(browser){const owned=browser;browser=null;await owned.close({silent:true});}};
  process.once('SIGTERM',()=>{closeBrowser().finally(()=>process.exit(1));});
  const onBrowserLog = ({text}) => {
    if(!text.startsWith(RUNTIME_PREFIX)) {
      if(messages.join('\n').length<limit)messages.push(bounded(text));
      progress(text);
      return;
    }
    try {const candidate=JSON.parse(text.slice(RUNTIME_PREFIX.length));
      if(candidate.session===request.session&&candidate.composition===request.composition&&candidate.frame===request.frame)record=candidate;
    } catch { /* Geçersiz kayıt gözlem kanıtı değildir. */ }
  };
  try {
    stage='browser';progress();
    const browserExecutable=installedBrowser(localRequire);
    browser=await renderer.openBrowser('chrome',{browserExecutable,chromeMode:'headless-shell',onBrowserDownload:()=>{throw new Error('Gözlem tarayıcı indiremez.');}});
    stage='bundle';progress();
    const serveUrl=await bundler.bundle({entryPoint:request.entry});
    const inputProps={__fusionRuntimeSession:request.session};
    stage='select';progress();
    const composition=await renderer.selectComposition({serveUrl,id:request.composition,inputProps,puppeteerInstance:browser,onBrowserLog,timeoutInMilliseconds:request.timeoutMs});
    stage='render';progress();
    await renderer.renderStill({serveUrl,composition,inputProps,frame:request.frame,
      output:request.artifact,imageFormat:'png',puppeteerInstance:browser,timeoutInMilliseconds:request.timeoutMs,onBrowserLog});
    stage='done';emit({record,rendered:true});
  } catch(error) {emit({record,rendered:false,error:bounded(String(error)+'\n'+messages.join('\n'))});process.exitCode=1;}
  finally {await closeBrowser();}
}
main().catch(error=>{process.stdout.write(JSON.stringify({error:String(error)}));process.exitCode=1;});

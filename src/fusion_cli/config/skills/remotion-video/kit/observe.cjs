// Kaynak/model beyanı değil: renderer'ın tarayıcı konsolundaki oturum kaydı.
const path = require('node:path');
const {createRequire} = require('node:module');
const RUNTIME_PREFIX = 'FUSION_RUNTIME_V1:';
async function main() {
  const request = JSON.parse(process.argv[2]);
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
  catch {process.stdout.write(JSON.stringify({error:'Mevcut renderer/bundler kurulu değil.'}));process.exitCode=1;return;}
  let record = null, browser = null;
  const closeBrowser = async () => {if(browser){const owned=browser;browser=null;await owned.close({silent:true});}};
  process.once('SIGTERM',()=>{closeBrowser().finally(()=>process.exit(1));});
  const onBrowserLog = ({text}) => {
    if(!text.startsWith(RUNTIME_PREFIX))return;
    try {const candidate=JSON.parse(text.slice(RUNTIME_PREFIX.length));
      if(candidate.session===request.session&&candidate.composition===request.composition&&candidate.frame===request.frame)record=candidate;
    } catch { /* Geçersiz kayıt gözlem kanıtı değildir. */ }
  };
  try {
    browser=await renderer.openBrowser('chrome');
    const serveUrl=await bundler.bundle({entryPoint:request.entry});
    const inputProps={__fusionRuntimeSession:request.session};
    const composition=await renderer.selectComposition({serveUrl,id:request.composition,inputProps,puppeteerInstance:browser});
    await renderer.renderStill({serveUrl,composition,inputProps,frame:request.frame,
      output:request.artifact,imageFormat:'png',puppeteerInstance:browser,timeoutInMilliseconds:request.timeoutMs,onBrowserLog});
    process.stdout.write(JSON.stringify({record,rendered:true}));
  } catch(error) {process.stdout.write(JSON.stringify({record,rendered:false,error:String(error)}));process.exitCode=1;}
  finally {await closeBrowser();}
}
main().catch(error=>{process.stdout.write(JSON.stringify({error:String(error)}));process.exitCode=1;});

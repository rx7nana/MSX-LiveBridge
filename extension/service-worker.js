const HOST='com.msxlivebridge.connect';
let connection=null, retryAt=0, queue=Promise.resolve();
// Only a PLAY admitted by this application instance may own later controls.
let owner=null;
let restored=false;
async function saveOwner() { await chrome.storage.session.set({owner}); }
async function restoreOwner() {
  if(!restored) { owner=(await chrome.storage.session.get('owner')).owner??null;restored=true; }
}
async function discover() {
  if(connection) return connection;
  if(Date.now()<retryAt) return null;
  try {
    const result=await chrome.runtime.sendNativeMessage(HOST,{action:'connect'});
    if(!result?.connected || !/^[A-Za-z0-9_-]{40,64}$/.test(result.token)
       || result.port!==27183 || !/^[a-f0-9]{32}$/.test(result.instance)) throw Error('unavailable');
    connection=result;return connection;
  } catch {retryAt=Date.now()+1000;return null;}
}
async function forward(request,sender) {
  await restoreOwner();
  const current=await discover();
  if(!current) return {connected:false};
  const key=`${sender.tab.id}:${request.session}`;
  if(request.action!=='play' && (!owner || owner.key!==key || owner.instance!==current.instance)) return {accepted:false};
  if(request.action==='play') {
    if(typeof request.mgs!=='string' || request.mgs.length>12*1024*1024) return {accepted:false};
    const bytes=Uint8Array.from(atob(request.mgs),c=>c.charCodeAt(0));
    request.sha256=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),v=>v.toString(16).padStart(2,'0')).join('');
  }
  try {
    const response=await fetch(`http://127.0.0.1:${current.port}/command`,{
      method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${current.token}`},
      body:JSON.stringify(request),signal:AbortSignal.timeout(3000)});
    if(!response.ok) throw Error('disconnected');
    const result=await response.json();
    if(request.action==='play' && result.accepted) owner={key,instance:current.instance};
    if(request.action==='stop') owner=null;
    await saveOwner();
    // Do not send tokens, HTTP errors, or engine diagnostics back into the page.
    return {connected:true,accepted:result.accepted===true};
  } catch {
    connection=null;owner=null;retryAt=0;await saveOwner();
    // Retry only PLAY after an app restart. Old controls never target new music.
    const fresh=await discover();
    if(request.action==='play' && fresh && fresh.instance!==current.instance) return forward(request,sender);
    return {connected:false};
  }
}
chrome.runtime.onMessage.addListener((message,sender,reply)=>{
  if(sender.id!==chrome.runtime.id || !sender.tab || sender.frameId!==0
      || !sender.url?.startsWith('https://msxplay.com/') || message?.type!=='command') return false;
  const request=message.request;
  if(!request || !['play','pause','resume','stop','seek','ending'].includes(request.action)
      || typeof request.session!=='string' || !Number.isSafeInteger(request.sequence)) return false;
  queue=queue.then(()=>forward(request,sender)).then(reply).catch(()=>reply({connected:false}));
  return true;
});
function stopTab(tabId) {
  queue=queue.then(async()=>{
    await restoreOwner();
    if(!owner || !owner.key.startsWith(`${tabId}:`))return;
    await discover();
    if(!connection || connection.instance!==owner.instance) {owner=null;await saveOwner();return;}
    // A closed page cannot own continuing hardware playback.
    await fetch(`http://127.0.0.1:${connection.port}/command`,{
      method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${connection.token}`},
      body:JSON.stringify({action:'stop',session:owner.key.slice(owner.key.indexOf(':')+1),sequence:Number.MAX_SAFE_INTEGER}),
      signal:AbortSignal.timeout(3000)}).catch(()=>{});
    owner=null;await saveOwner();
  }).catch(()=>{});
}
chrome.tabs.onRemoved.addListener(stopTab);
chrome.tabs.onUpdated.addListener((tabId,change)=>{if(change.status==='loading')stopTab(tabId);});

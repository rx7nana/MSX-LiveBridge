import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import vm from 'node:vm';
import {test} from 'node:test';
const source=readFileSync(new URL('../extension/service-worker.js',import.meta.url),'utf8');
const id='fcebnajmcgjhmkbgefjgaaadnjpdamnc';
const sender={id,tab:{id:7},frameId:0,url:'https://msxplay.com/'};
function harness({storage={},offline=false}={}){
 let listener,closed,updated;let online=!offline,instance='a'.repeat(32),token='x'.repeat(43),clock=0;
 const calls=[],native=[];
 const context=vm.createContext({Uint8Array,atob,crypto:webcrypto,AbortSignal,Date:{now:()=>clock},chrome:{
  runtime:{id,onMessage:{addListener:f=>listener=f},sendNativeMessage:async(host,data)=>{native.push({host,data});return online?{connected:true,instance,token,port:27183}:{connected:false}}},
  tabs:{onRemoved:{addListener:f=>closed=f},onUpdated:{addListener:f=>updated=f}},storage:{session:{get:async()=>storage,set:async v=>Object.assign(storage,v)}}},
  fetch:async(url,args)=>{calls.push({url,...args,request:JSON.parse(args.body)});if(!online||args.headers.Authorization!==`Bearer ${token}`)throw Error('offline');return {ok:true,json:async()=>({accepted:true})};}});
 vm.runInContext(source,context);
 let seq=0;
 return {calls,native,storage,context,
  send(action,extra={},from=sender){return new Promise(resolve=>{const request={action,session:'page',sequence:++seq,...(action==='play'?{mgs:btoa('MGS3abc'),durationMs:300000}:{}),...extra};if(!listener({type:'command',request},from,resolve))resolve({rejected:true});});},
  restart(){instance='b'.repeat(32);token='z'.repeat(43);},
  online(value){online=value;clock+=2000;},
  async navigate(){updated(7,{status:"loading"});await vm.runInContext("queue",context);},
  async close(){closed(7);await vm.runInContext('queue',context);}
 };
}
test('offline app: no HTTP and no user-facing error',async()=>{const h=harness({offline:true});assert.equal((await h.send('play')).connected,false);assert.equal(h.calls.length,0);});
test('late app launch connects on next PLAY with no extension action',async()=>{const h=harness({offline:true});await h.send('play');h.online(true);assert.equal((await h.send('play')).accepted,true);assert.equal(h.calls.length,1);});
test('authenticated ordered controls include natural ending metadata',async()=>{const h=harness();await Promise.all([h.send('play'),h.send('pause'),h.send('seek',{targetMs:2000}),h.send('resume'),h.send('ending',{playSequence:1,fadeDurationMs:5000,sampleRate:48000,bufferedMs:165000,isFaded:true})]);assert.deepEqual(h.calls.map(x=>x.request.action),['play','pause','seek','resume','ending']);assert.equal(h.calls[0].request.sha256.length,64);assert.equal(h.calls[4].request.bufferedMs,165000);assert.ok(h.calls.every(x=>x.headers.Authorization==='Bearer '+'x'.repeat(43)));});
test('credentials are never returned to page/content',async()=>{const h=harness();const reply=await h.send('play');assert.deepEqual(Object.keys(reply).sort(),['accepted','connected']);assert.ok(h.native.every(x=>x.host==='com.msxlivebridge.connect'));});
test('service worker suspension restores owner without changing musical state',async()=>{const first=harness();await first.send('play');const second=harness({storage:first.storage});assert.equal((await second.send('pause')).accepted,true);assert.equal(second.calls[0].request.action,'pause');});
test('app restart rejects old controls; subsequent PLAY reconnects',async()=>{const h=harness();await h.send('play');h.restart();assert.equal((await h.send('pause')).connected,false);assert.equal((await h.send('resume')).accepted,false);assert.equal((await h.send('play')).accepted,true);});
test('new PLAY after app restart retries once using new credentials',async()=>{const h=harness();await h.send('play');h.restart();assert.equal((await h.send('play')).accepted,true);assert.equal(h.calls.at(-1).headers.Authorization,'Bearer '+'z'.repeat(43));});
test('another tab and old page cannot pause current owner',async()=>{const h=harness();await h.send('play');await h.send('pause',{}, {...sender,tab:{id:8}});await h.send('pause',{session:'old'});assert.equal(h.calls.length,1);});
test('untrusted URL/frame/extension messages rejected before discovery',async()=>{const h=harness();for(const from of [{...sender,url:'https://evil.example/'},{...sender,frameId:1},{...sender,id:'other'}])assert.equal((await h.send('play',{},from)).rejected,true);assert.equal(h.native.length,0);});
test('closing the owning tab stops hardware and clears ownership',async()=>{const h=harness();await h.send('play');await h.close();assert.equal(h.calls.at(-1).request.action,'stop');assert.equal(h.storage.owner,null);});

test('tab closure after worker suspension restores ownership before stopping',async()=>{const a=harness();await a.send('play');const b=harness({storage:a.storage});await b.close();assert.equal(b.calls.at(-1).request.action,'stop');});
test('page navigation stops old playback without replaying data',async()=>{const h=harness();await h.send('play');await h.navigate();assert.deepEqual(h.calls.map(x=>x.request.action),['play','stop']);});

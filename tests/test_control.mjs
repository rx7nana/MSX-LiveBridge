import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {test} from 'node:test';
import {webcrypto} from 'node:crypto';
const main=readFileSync(new URL('../extension/main-hook.js',import.meta.url),'utf8');
function harness({ending=false}={}) {
  let install;
  const calls=[], messages=[];
  const player={kss:{data:new Uint8Array([77,71,83,51,5])}};
  const listeners={};
  if(ending)Object.assign(player,{sampleRate:48000,playArgs:{duration:300000,fadeDuration:5000},audioPlayer:{player:{
    progress:{renderer:{isFulFilled:false,bufferedTime:0},decoder:{status:{isFaded:false}}},
    addEventListener:(event,cb)=>listeners[event]=cb
  }}});
  for(const method of ['play','pause','resume','stop','seekTo']) player[method]=function(...args){calls.push([method,this,...args]);return method;};
  const context=vm.createContext({window:{MSXPlayUI:{msxplay:player}},Uint8Array,crypto:webcrypto,
    BroadcastChannel:class{postMessage(x){messages.push(x);}},setInterval:cb=>(install=cb,1),clearInterval(){}});
  vm.runInContext(main,context);install();
  return {player,calls,messages,install,listeners};
}
for(const method of ['play','pause','resume','stop','seekTo']) test(`${method}: immediate original call, same receiver, args and result`,()=>{
  const h=harness(); assert.equal(h.player[method](123,'extra'),method);
  assert.deepEqual(h.calls[0],[method,h.player,123,'extra']);
  assert.equal(h.messages.at(-1).action,method==='seekTo'?'seek':method);
});
test('PLAY uses an independent MGS copy; edited compile captures new content',()=>{
  const h=harness(); h.player.play(); const first=h.messages.at(-1);
  h.player.kss.data[4]=9; assert.equal(first.bytes[4],5);
  h.player.stop();h.player.play();assert.equal(h.messages.at(-1).bytes[4],9);
  assert.equal(h.messages.at(-1).sequence,3);
});
test('rapid SEEK / PAUSE / RESUME preserve operation order without timers',()=>{
  const h=harness(); for(const x of [20000,2000,4000])h.player.seekTo(x);
  h.player.pause();h.player.resume();
  assert.deepEqual(h.messages.filter(x=>x.kind==='command').map(x=>x.sequence),[1,2,3,4,5]);
  assert.equal(h.calls.length,5);
});
test('install is idempotent and browser volume/stream API are untouched',()=>{
  const h=harness();const original=h.player.play;h.install();assert.equal(h.player.play,original);
  assert.equal(h.player.setMasterVolume,undefined);
});
test('ending metadata comes only from new completed PCM, with actual fade setting and rate',()=>{
  const h=harness({ending:true});h.player.play();
  h.player.audioPlayer.player.progress={renderer:{isFulFilled:true,bufferedTime:165000},decoder:{isDecoding:false,status:{isFaded:true}}};
  h.listeners.progress();assert.equal(h.messages.at(-1).action,'play');
  h.listeners.statechange({detail:'playing'});h.listeners.progress();
  const m=h.messages.at(-1);assert.equal(m.action,'ending');assert.equal(m.playSequence,1);
  assert.equal(m.fadeDurationMs,5000);assert.equal(m.sampleRate,48000);assert.equal(m.bufferedMs,165000);
  const count=h.messages.length;h.listeners.progress();assert.equal(h.messages.length,count);
  assert.equal(h.calls.length,1);
});
test('STOP discards old ending observer; PAUSE does not manufacture a fade event',()=>{
  const h=harness({ending:true});h.player.play();h.listeners.statechange({detail:'playing'});
  h.player.pause();h.listeners.progress();assert.equal(h.messages.at(-1).action,'pause');
  h.player.stop();h.player.audioPlayer.player.progress.renderer={isFulFilled:true,bufferedTime:165000};
  h.listeners.progress();assert.equal(h.messages.at(-1).action,'stop');
});

test('renderer completion waits for final decoder status across message ports',()=>{
  const h=harness({ending:true});h.player.play();h.listeners.statechange({detail:'playing'});
  const p=h.player.audioPlayer.player.progress;
  p.renderer={isFulFilled:true,bufferedTime:165000};p.decoder={isDecoding:true,status:{isFaded:false}};
  h.listeners.progress();assert.equal(h.messages.at(-1).action,'play');
  p.decoder={isDecoding:false,status:{isFaded:true}};h.listeners.progress();
  assert.equal(h.messages.at(-1).action,'ending');assert.equal(h.messages.at(-1).isFaded,true);
});


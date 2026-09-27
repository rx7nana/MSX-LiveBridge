// The page never receives credentials or a privileged HTTP interface.
const channel = new BroadcastChannel('msx-livebridge');
let queue = Promise.resolve();
channel.onmessage = ({data}) => {
  if (data?.kind !== 'command') return;
  queue = queue.then(async () => {
    const {action, session, sequence} = data;
    const request = {action,session,sequence};
    if (action === 'play') {
      if (!(data.bytes instanceof Uint8Array)) return;
      let binary='';
      for(let i=0;i<data.bytes.length;i+=8192) binary+=String.fromCharCode(...data.bytes.subarray(i,i+8192));
      request.mgs=btoa(binary);
      request.durationMs=data.durationMs;
    } else if (action==='seek') request.targetMs=data.targetMs;
    else if (action==='ending') {
      for(const key of ['playSequence','fadeDurationMs','sampleRate','bufferedMs','isFaded']) request[key]=data[key];
    }
    await chrome.runtime.sendMessage({type:'command',request});
  }).catch(()=>{}); // Desktop closed: browser playback remains independent.
};

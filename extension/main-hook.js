(() => {
  const channel = new BroadcastChannel('msx-livebridge');
  const session = crypto.randomUUID();
  let sequence = 0;
  function notify(action, extra = {}) {
    channel.postMessage({kind:'command', session, sequence:++sequence, action, ...extra});
  }
  function install() {
    const player = window.MSXPlayUI?.msxplay;
    if (!player || player.__msxLiveBridgeInstalled) return false;
    let ending = null;
    const stream = player.audioPlayer?.player;
    const publishEnding = () => {
      const progress = stream?.progress;
      if (!ending?.started || !ending.announced || !progress?.renderer?.isFulFilled
          || progress.decoder?.isDecoding !== false) return;
      const metadata = ending;
      ending = null;
      // This describes the finished PCM buffer, never the browser wall clock.
      notify('ending', {playSequence:metadata.playSequence, fadeDurationMs:metadata.fadeDurationMs,
        sampleRate:metadata.sampleRate, bufferedMs:progress.renderer.bufferedTime,
        isFaded:progress.decoder?.status?.isFaded === true});
    };
    stream?.addEventListener('statechange', event => {
      if (ending && event.detail === 'playing') ending.started = true;
    });
    stream?.addEventListener('progress', publishEnding);
    for (const method of ['play', 'pause', 'resume', 'stop', 'seekTo']) {
      const original = player[method];
      if (typeof original !== 'function') continue;
      player[method] = function (...args) {
        // Copy before play; never mutate the source or wait for Windows.
        const bytes = method === 'play' && this.kss?.data instanceof Uint8Array
          ? new Uint8Array(this.kss.data) : undefined;
        if (method === 'stop') ending = null;
        if (method === 'play') ending = {
          playSequence:sequence+1, fadeDurationMs:this.playArgs?.fadeDuration,
          sampleRate:this.sampleRate, started:false, announced:false
        };
        const result = original.apply(this, args);
        if (method === 'play' && !bytes) {
          channel.postMessage({kind:'capture-error', error:'MGS data is unavailable'});
        } else {
          notify(method === 'seekTo' ? 'seek' : method,
            method === 'play' ? {bytes,durationMs:this.playArgs?.duration} : method === 'seekTo' ? {targetMs:args[0]} : {});
        }
        if (method === 'play' && ending) { ending.announced = true; publishEnding(); }
        return result;
      };
    }
    player.__msxLiveBridgeInstalled = true;
    channel.postMessage({kind:'hook-installed'});
    return true;
  }
  const timer = setInterval(() => { if (install()) clearInterval(timer); }, 20);
})();

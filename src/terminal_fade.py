"""PCM-ending metadata, derived from libkss-js 2.2.1's integer linear fader."""
import math

def ending_plan(request):
    rate, duration, buffered = (request.get(key) for key in ('sampleRate','fadeDurationMs','bufferedMs'))
    if any(type(x) not in (int,float) or not math.isfinite(x) for x in (rate,duration,buffered)):
        raise ValueError('finite PCM ending metadata required')
    if not 8000 <= rate <= 192000 or not 0 <= duration <= 1200000 or not 0 <= buffered <= 1201000:
        raise ValueError('PCM ending metadata out of range')
    if type(request.get('isFaded')) is not bool: raise ValueError('isFaded required')
    duration = int(duration)
    if not request['isFaded'] or duration == 0:
        return dict(start_sample=round(buffered*44.1),end_sample=round(buffered*44.1),rate=round(rate),step=0)
    # Mono KSSPlay: fade starts at 2^31; each PCM frame subtracts floor(2^31 / N).
    frames = max(1, int(rate*duration/1000))
    step = max(1,(1<<31)//frames)
    actual_frames = ((1<<31)+step-1)//step
    # Decoder emits one second at a time, including the final partly silent chunk.
    chunks = (actual_frames+int(rate)-1)//int(rate)
    start_ms = max(0,buffered-chunks*1000)
    return dict(start_sample=round(start_ms*44.1),
                end_sample=round(start_ms*44.1)+math.ceil(actual_frames*44100/rate),
                rate=round(rate),step=step)

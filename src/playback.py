"""Ordered playback intent and cached MGS/write data; Native owns the music clock."""
from __future__ import annotations
import base64
import hashlib
import json
import math
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from encoder import build
from terminal_fade import ending_plan

SAMPLE_RATE = 44100


def parse_vgm_writes(path: Path) -> tuple[list[dict], dict]:
    raw = path.read_bytes()
    if raw[:4] != b"Vgm ":
        raise ValueError("kss2vgm did not produce a VGM file")
    data_offset = int.from_bytes(raw[0x34:0x38], "little")
    pc = 0x34 + (data_offset or 0x0C)
    sample = ordinal = 0
    writes: list[dict] = []
    counts = {"PSG": 0, "YM2413": 0, "SCC": 0}

    def emit(chip: str, address: int, data: int) -> None:
        nonlocal ordinal
        writes.append({"kind": "write", "ordinal": ordinal, "sample": sample,
                       "time_us": round(sample * 1_000_000 / SAMPLE_RATE, 9),
                       "chip": chip, "address": address, "data": data})
        ordinal += 1
        counts[chip] += 1

    while pc < len(raw):
        command = raw[pc]
        pc += 1
        if command == 0x66:
            break
        if command == 0x51:  # YM2413: register, value
            emit("YM2413", raw[pc], raw[pc + 1]); pc += 2; continue
        if command == 0xA0:  # AY-3-8910: register, value
            emit("PSG", raw[pc], raw[pc + 1]); pc += 2; continue
        if command == 0xD2:  # K051649/SCC: port, register, value
            emit("SCC", (raw[pc] << 8) | raw[pc + 1], raw[pc + 2]); pc += 3; continue
        if command == 0x61:
            sample += int.from_bytes(raw[pc:pc + 2], "little"); pc += 2; continue
        if command == 0x62:
            sample += 735; continue
        if command == 0x63:
            sample += 882; continue
        if 0x70 <= command <= 0x7F:
            sample += (command & 0x0F) + 1; continue
        if command == 0x67 and raw[pc] == 0x66:
            size = int.from_bytes(raw[pc + 2:pc + 6], "little")
            pc += 6 + size; continue
        raise ValueError(f"unsupported VGM command 0x{command:02x} at 0x{pc - 1:x}")
    return writes, {"samples": sample, **counts}


@dataclass
class Playback:
    session: str = ''
    sequence: int = 0
    generation: int = 0
    desired: str = 'stopped'
    target_ms: int = 0
    media: dict | None = None
    active: tuple | None = None
    error: str | None = None

class Superseded(Exception):
    pass

class Bridge:
    def __init__(self, output, kss2vgm, seconds, token, sender, sender_options=None, converter_started=None):
        self.output, self.kss2vgm, self.seconds = Path(output), Path(kss2vgm), seconds
        self.token, self.sender = token, Path(sender)
        self.sender_options = sender_options or (lambda: ("FT232H", []))
        self.converter_started = converter_started
        self.output.mkdir(parents=True, exist_ok=True)
        self.log_path = self.output/'bridge-events.jsonl'
        self.changed = threading.Condition(threading.RLock())
        self.state = Playback()
        self.retired_sessions = set()
        self.closed = False
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def log(self, value):
        with self.changed, self.log_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(value, ensure_ascii=False)+'\n')

    @staticmethod
    def write_control(path, value):
        temp = path.with_suffix('.tmp')
        temp.write_text(value+'\n', encoding='ascii')
        for attempt in range(50):
            try:
                temp.replace(path)
                return
            except PermissionError:
                if attempt == 49: raise
                time.sleep(.002)

    def command(self, request):
        action = request.get('action')
        if action == 'status': return self.status()
        if action == 'ending':
            plan = ending_plan(request)
            with self.changed:
                s = self.state
                if request.get('session') != s.session or not s.media or request.get('playSequence') != s.media['play_sequence']:
                    return {'accepted':False,'reason':'obsolete ending metadata'}
                s.media['ending'] = plan
                if s.active and s.active[3] == s.generation and s.active[0].poll() is None:
                    self.write_control(s.active[2].with_suffix('.ending.json'),json.dumps(plan,separators=(',',':')))
                self.log(dict(kind='ending-ready',mgs_sha256=s.media['sha256'],**plan))
                return {'accepted':True,'ending':plan}
        if action not in {'play','pause','resume','stop','seek'}: raise ValueError('unknown action')
        session, sequence = request.get('session'), request.get('sequence')
        if not isinstance(session,str) or not 1 <= len(session) <= 128: raise ValueError('session required')
        if type(sequence) is not int or sequence < 1: raise ValueError('positive sequence required')
        target = request.get('targetMs',0)
        if action == 'seek' and (type(target) not in (int,float) or not math.isfinite(target) or not 0 <= target <= 3600000):
            raise ValueError('invalid seek target')
        media = None
        if action == 'play':
            duration_ms = request.get('durationMs',self.seconds*1000)
            if type(duration_ms) not in (int,float) or not math.isfinite(duration_ms) or not 0 < duration_ms <= 1200000:
                raise ValueError('invalid durationMs')
            data = base64.b64decode(request.get('mgs',''), validate=True)
            digest = hashlib.sha256(data).hexdigest()
            if not data.startswith(b'MGS3') or len(data)>8*1024*1024: raise ValueError('invalid MGS3')
            if request.get('sha256') != digest: raise ValueError('MGS SHA-256 mismatch')
            media = dict(data=data, sha256=digest, writes=None, summary=None, path=None,
                         play_sequence=sequence,ending=None,render_seconds=math.ceil(duration_ms/1000))
        with self.changed:
            s = self.state
            # A new page takes ownership only with PLAY. Old-page controls cannot touch it.
            if session != s.session:
                if session in self.retired_sessions: return {'accepted':False,'reason':'retired session'}
                if action != 'play': return {'accepted':False,'reason':'inactive session'}
                if s.session: self.retired_sessions.add(s.session)
            elif sequence <= s.sequence:
                return {'accepted':False,'reason':'stale sequence'}
            s.session, s.sequence, s.error = session, sequence, None
            replace = action in {'play','seek','stop'}
            if action == 'play': s.media, s.target_ms, s.desired = media, 0, 'playing'
            elif action == 'seek':
                if not s.media: raise ValueError('no captured music')
                s.target_ms = round(target)
                # A paused seek stays paused; seeking stopped music prepares a paused position.
                if s.desired == 'stopped': s.desired = 'paused'
            elif action == 'stop': s.desired = 'stopped'
            elif action == 'pause' and s.desired != 'stopped': s.desired = 'paused'
            elif action == 'resume' and s.desired == 'paused': s.desired = 'playing'
            if replace: s.generation += 1
            if s.active and s.active[0].poll() is None:
                self.write_control(s.active[1], 'stop' if replace else ('pause' if s.desired=='paused' else 'run'))
            self.changed.notify_all()
            result = {'accepted':True,'sequence':sequence,'generation':s.generation,'desired':s.desired}
            self.log({'kind':'command', 'action':action, **result})
            return result

    def status(self):
        with self.changed:
            s = self.state
            native = None
            if s.active:
                try: native = json.loads(s.active[2].read_text(encoding='utf-8'))
                except (OSError,ValueError): pass
            return dict(desired=s.desired, target_ms=s.target_ms, generation=s.generation,
                        mgs_sha256=s.media['sha256'] if s.media else None,
                        native=native, native_generation=s.active[3] if s.active else None, error=s.error)

    def check(self, generation):
        with self.changed:
            if self.closed or generation != self.state.generation: raise Superseded()

    def convert(self, media, target, generation):
        needed = max(self.seconds, media['render_seconds'], target//1000+10)
        if media['writes'] is not None and (target*44.1 <= media['summary']['samples']): return
        stem = self.output/f'media-{media["sha256"][:12]}-{uuid.uuid4().hex[:8]}'
        mgs, vgm = stem.with_suffix('.mgs'), stem.with_suffix('.vgm')
        mgs.write_bytes(media['data'])
        # Only one converter runs; newer operations cancel it without opening FTDI.
        with stem.with_suffix('.converter.log').open('w',encoding='utf-8') as log:
            p = subprocess.Popen([str(self.kss2vgm),f'-p{needed}',f'-o{vgm}',str(mgs)],
                                 stdout=log,stderr=subprocess.STDOUT,
                                 creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                if self.converter_started:self.converter_started(p)
                deadline = time.monotonic()+90
                while p.poll() is None:
                    self.check(generation)
                    if time.monotonic()>deadline: raise RuntimeError('MGS conversion timed out')
                    time.sleep(.01)
                if p.returncode: raise RuntimeError(f'MGS conversion failed: {p.returncode}')
            finally:
                if p.poll() is None: p.terminate(); p.wait(timeout=5)
        self.check(generation)
        writes, summary = parse_vgm_writes(vgm)
        media.update(writes=writes, summary=summary, path=mgs)
        self.log(dict(kind='media-ready',mgs_sha256=media['sha256'],vgm_sha256=hashlib.sha256(vgm.read_bytes()).hexdigest(),writes=summary))

    def stop_active(self):
        with self.changed:
            active = self.state.active
            if active and active[0].poll() is None: self.write_control(active[1],'stop')
        if active:
            # Never open a second FTDI handle before the old sender has closed it.
            active[0].wait(timeout=5)
            with self.changed:
                if self.state.active is active: self.state.active = None

    def prepare(self, generation, media, target):
        self.stop_active()
        self.check(generation)
        self.convert(media,target,generation)
        self.check(generation)
        target = min(target, round(media['summary']['samples']/44.1))
        stem = self.output/f'playback-{generation}-{uuid.uuid4().hex[:8]}'
        batch, control, status = stem.with_suffix('.batches.jsonl'), stem.with_suffix('.control'), stem.with_suffix('.status.json')
        build(media['writes'],batch,target,media['summary']['samples'])
        with self.changed:
            self.check(generation)
            self.write_control(control,'pause' if self.state.desired=='paused' else 'run')
            if media['ending']:
                self.write_control(status.with_suffix('.ending.json'),json.dumps(media['ending'],separators=(',',':')))
            with stem.with_suffix('.sender.log').open('w',encoding='utf-8') as log:
                profile, options = self.sender_options()
                p = subprocess.Popen([str(self.sender),profile,'play',str(batch),str(control),str(status),*options],
                                     stdout=log,stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            self.state.active = (p,control,status,generation)
            self.log(dict(kind='sender-start',generation=generation,target_ms=target,pid=p.pid))

    def run(self):
        handled = -1
        while True:
            with self.changed:
                self.changed.wait_for(lambda: self.closed or self.state.generation!=handled, timeout=.1)
                if self.closed: break
                s = self.state
                if s.generation == handled:
                    if s.active and s.active[0].poll() is not None:
                        code = s.active[0].returncode
                        if code: s.error = f'Native Sender exited {code}; see sender log'
                        s.desired = 'stopped'
                    continue
                generation, media, target, desired = s.generation,s.media,s.target_ms,s.desired
                handled = generation
            try:
                if desired == 'stopped': self.stop_active()
                elif media: self.prepare(generation,media,target)
            except Superseded:
                continue
            except Exception as error:
                with self.changed:
                    if generation == self.state.generation:
                        self.state.error, self.state.desired = str(error),'stopped'
                        if self.state.active and self.state.active[0].poll() is None:
                            self.write_control(self.state.active[1],'stop')
                self.log(dict(kind='playback-error',generation=generation,error=str(error)))
        self.stop_active()

    def close(self):
        with self.changed:
            self.closed = True
            if self.state.active and self.state.active[0].poll() is None: self.write_control(self.state.active[1],'stop')
            self.changed.notify_all()
        self.worker.join(timeout=8)
        if self.worker.is_alive(): raise RuntimeError('Bridge worker did not stop')

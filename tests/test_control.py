import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import playback as module
from encoder import build, convert
from vsif_decode import decode_batches
SENDER=ROOT/'tests/mock-bin/msx-vsif-sender.exe'
FIX=Path(os.environ.get('MSXLB_TEST_FIXTURES',ROOT/'tests/fixtures')).resolve()
CONVERTER=Path(os.environ.get('MSXLB_KSS2VGM',ROOT/'vendor/kss2vgm.exe')).resolve()
def frame(t,a,d):return bytes([0x20|t,a>>4,0x10|(a&15),d>>4,0x10|(d&15)])
def fixture_bytes(name):
    path=FIX/name
    if not path.is_file():raise unittest.SkipTest('Optional private fixture missing: '+name)
    if name.endswith('.mgs') and not CONVERTER.is_file():raise unittest.SkipTest('Prepare kss2vgm or set MSXLB_KSS2VGM')
    return path.read_bytes()

def rows(path):
    if path.is_relative_to(FIX) and not path.is_file():raise unittest.SkipTest('Optional private fixture missing: '+path.name)
    return [json.loads(x) for x in path.read_text().splitlines()]
def wait(predicate,timeout=5):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        time.sleep(.01)
    raise AssertionError('condition timeout')
def native_status(path):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {}

class Native(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.processes=[]
    def tearDown(self):
        for p in self.processes:
            if p.poll() is None:p.kill()
            p.communicate(timeout=5)
        self.temp.cleanup()
    def start(self,paused=False,snapshot=False,**options):
        self.control=self.path/'control';module.Bridge.write_control(self.control,'pause' if paused else 'run')
        self.status=self.path/'state.json'; self.log=self.path/'writes.jsonl'
        pre=frame(0x17,0,20)+frame(1,0x10,55)+frame(4,0,127)
        gate=frame(0x17,8,12)+frame(1,0x20,0x15)+frame(4,0xaa,15)
        batch=[dict(bin=-2 if snapshot else -1,sample=44100 if snapshot else 0,hex=pre.hex())]
        base=44100 if snapshot else 0
        if snapshot:batch.append(dict(bin=-3,sample=base,hex=gate.hex()))
        batch.extend([dict(bin=0,sample=base+4410,hex=frame(1,0x11,77).hex()),
                      dict(bin=1,sample=base+22050,hex=bytes([0x20,0,0x12]).hex()),
                      dict(bin=2,sample=base+88200,hex='')])
        f=self.path/'batch';f.write_text('\n'.join(json.dumps(x,separators=(',',':')) for x in batch))
        env=dict(os.environ,FAKE_LOG=str(self.log),**{k:str(v) for k,v in options.items()})
        p=subprocess.Popen([str(SENDER),'FT232H','play',str(f),str(self.control),str(self.status)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.processes.append(p);return p,pre,gate
    def sent(self):
        return [bytes.fromhex(x['hex'])[::32] for x in rows(self.log)]
    def state(self,state):return wait(lambda:native_status(self.status).get('state')==state)
    def command(self,action):module.Bridge.write_control(self.control,action)
    def test_play_tempo_initial_noise_split_and_end_mute(self):
        p,pre,_=self.start();self.state('playing');p.wait(timeout=5)
        sent=self.sent();self.assertEqual(sent[1],pre)
        self.assertEqual(sent[2],frame(1,0x11,77));self.assertEqual(sent[3],bytes([0x20,0,0x12]))
        times=[x['at'] for x in rows(self.log)]
        self.assertGreater(times[2]-times[1],.58)
        self.assertAlmostEqual(times[3]-times[2],.4,delta=.06)
        self.assertIn(frame(0x17,8,0),sent[-1]);self.assertIn(frame(4,0xaf,0),sent[-1])
        self.assertEqual(p.returncode,0)
    def test_pause_freezes_position_and_resume_repairs_compressed_cursor(self):
        p,_,_=self.start();wait(lambda:self.log.exists() and len(rows(self.log))>=3)
        self.command('pause');self.state('paused');pos=native_status(self.status)['sample'];n=len(rows(self.log))
        time.sleep(.2);self.assertEqual(native_status(self.status)['sample'],pos);self.assertEqual(len(rows(self.log)),n)
        self.command('run');self.state('playing');wait(lambda:frame(1,0x12,2) in self.sent())
        self.command('stop');p.wait(timeout=3);self.assertEqual(p.returncode,0)
    def test_paused_seek_restores_only_after_resume(self):
        p,pre,gate=self.start(paused=True,snapshot=True);self.state('paused')
        self.assertEqual(native_status(self.status)['sample'],44100)
        self.assertEqual(self.sent()[1],pre);self.assertNotIn(gate,self.sent())
        self.command('run');self.state('playing')
        self.assertTrue(any(frame(0x17,8,12) in x and frame(4,0xaa,15) in x for x in self.sent()))
        self.command('stop');p.wait(timeout=3)
    def test_stop_during_preparation_never_sends_gate(self):
        p,_,gate=self.start(snapshot=True);wait(lambda:self.log.exists() and len(rows(self.log))>=2)
        self.command('stop');p.wait(timeout=3);self.assertNotIn(gate,self.sent())
    def test_pause_during_preparation_is_retained(self):
        p,_,gate=self.start(snapshot=True);self.state('preparing');self.command('pause');self.state('paused')
        self.assertNotIn(gate,self.sent());self.command('stop');p.wait(timeout=3)
    def test_write_failure_and_queue_errors_fail_closed(self):
        for option in [dict(FAKE_SHORT_AT=2),dict(FAKE_STATUS_ERROR=1),dict(FAKE_STUCK=1)]:
            with self.subTest(option=option):
                p,_,_=self.start(**option);p.wait(timeout=5);self.assertNotEqual(p.returncode,0)
                self.assertEqual(native_status(self.status)['state'],'error');self.assertIn(frame(0x17,8,0),self.sent()[-1])
                self.log.unlink()
    def test_unknown_profile_and_missing_custom_values_rejected(self):
        for profile in ['Unknown','Custom']:
            r=subprocess.run([str(SENDER),profile,'play','x','y','z'],capture_output=True)
            self.assertEqual(r.returncode,3)

class Encoder(unittest.TestCase):
    def test_existing_music_and_snapshot_unchanged_except_ch5_waveform(self):
        writes=[x for x in rows(FIX/'writes.jsonl') if x.get('kind')=='write']
        with tempfile.TemporaryDirectory() as t:
            for target,name in [(0,'baseline-initial.jsonl'),(2431,'baseline-seek.jsonl')]:
                out=build(writes,Path(t)/'out',target,441000)
                baseline=rows(FIX/name)
                # Original write values/order remain, but the old 20ms buckets
                # intentionally no longer define the playback timestamps.
                actual=decode_batches(out[:-1])
                self.assertEqual([w for batch in actual for w in batch if not (w[0]==4 and 0x80<=w[1]<=0x9f)],
                                 [w for batch in decode_batches(baseline) for w in batch])
                self.assertEqual(out[-1]['sample'],441000)
    def test_all_scc_waveform_and_register_mapping(self):
        writes=[x for x in rows(FIX/'writes.jsonl') if x.get('kind')=='write']
        wave=[convert(x) for x in writes if x['chip']=='SCC' and x['address']>>8==0]
        self.assertEqual(len(wave),456);self.assertTrue(all(x[0]==4 for x in wave))
        self.assertEqual(convert(dict(chip='PSG',address=7,data=0x3f)),(0x17,7,0xbf))
    def test_seek_state_uses_only_writes_before_target(self):
        writes=[dict(kind='write',chip='PSG',address=8,data=d,sample=s) for s,d in [(0,1),(44100,2),(88200,3)]]
        with tempfile.TemporaryDirectory() as t:
            out=build(writes,Path(t)/'out',1000,100000)
            self.assertEqual(bytes.fromhex(out[2]['hex']),frame(0x17,8,1))
            self.assertEqual(bytes.fromhex(out[3]['hex']),frame(0x17,8,2))

class Bridge(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.seq=0
        self.env=patch.dict(os.environ,FAKE_LOG=str(self.path/'writes.jsonl'),FAKE_LIFECYCLE=str(self.path/'lifecycle.jsonl'));self.env.start()
        self.bridge=module.Bridge(self.path,CONVERTER,10,'token',SENDER)
    def tearDown(self):
        self.bridge.close();self.env.stop()
        path=self.path/'lifecycle.jsonl'
        if path.exists():
            active=None
            for event in rows(path):
                if event['event']=='open':self.assertIsNone(active,'two senders opened FTDI');active=event['pid']
                else:self.assertEqual(active,event['pid']);active=None
            self.assertIsNone(active,'sender did not close FTDI')
        self.temp.cleanup()
    def command(self,action,**extra):
        self.seq+=1
        if action=='play':
            data=extra.pop('data',fixture_bytes('contrail.mgs'))
            extra.update(mgs=base64.b64encode(data).decode(),sha256=hashlib.sha256(data).hexdigest())
        return self.bridge.command(dict(action=action,session='test',sequence=self.seq,**extra))
    def state(self,state,generation=None):
        return wait(lambda:(x:=self.bridge.status()).get('native') and x['native']['state']==state and x['native_generation']==x['generation'] and (generation is None or x['generation']==generation),10)
    def test_ending_metadata_tracks_media_across_seek_and_recompile(self):
        self.command('play');play_sequence=self.seq;self.state('playing')
        generation=self.bridge.state.generation
        metadata=dict(playSequence=play_sequence,sampleRate=44100,fadeDurationMs=5000,bufferedMs=165000,isFaded=True)
        self.assertTrue(self.command('ending',**metadata)['accepted'])
        self.assertEqual(self.bridge.state.generation,generation)
        plan=self.bridge.state.media['ending']
        self.assertTrue(self.bridge.state.active[2].with_suffix('.ending.json').exists())
        self.command('pause');self.state('paused')
        result=self.command('seek',targetMs=2000);self.state('paused',result['generation'])
        self.assertEqual(self.bridge.state.media['ending'],plan)
        self.command('resume');self.state('playing')
        self.command('stop');self.command('play');self.state('playing')
        self.assertIsNone(self.bridge.state.media['ending'])
        self.assertFalse(self.command('ending',**metadata)['accepted'])
        self.assertIsNone(self.bridge.state.media['ending'])

    def test_compile_repeat_edit_and_all_chip_writes(self):
        self.command('play');self.state('playing');first=self.bridge.state.media
        self.command('play');self.state('playing');wait(lambda:self.bridge.state.media['writes'] is not None)
        self.assertEqual(first['writes'],self.bridge.state.media['writes'])
        self.assertTrue(all(first['summary'][chip]>0 for chip in ['PSG','YM2413','SCC']))
        # Previously browser-captured edited MGS is an independent regression input.
        edited=fixture_bytes('edited.mgs')
        self.command('play',data=edited);wait(lambda:self.bridge.state.media['writes'] is not None,10)
        self.assertNotEqual(first['writes'],self.bridge.state.media['writes'])
    def test_forward_backward_continuous_seeks_pause_resume(self):
        self.command('play');self.state('playing')
        for target in [5000,2431,2431,0]:
            r=self.command('seek',targetMs=target);self.state('playing',r['generation'])
            wait(lambda:self.bridge.state.active and self.bridge.state.active[3]==r['generation'])
        self.command('pause');self.state('paused');self.command('resume');self.state('playing')
        self.command('pause');self.state('paused');r=self.command('seek',targetMs=2000)
        wait(lambda:self.bridge.state.active and self.bridge.state.active[3]==r['generation'])
        self.state('paused');self.assertEqual(self.bridge.status()['native']['sample'],88200)
        self.command('resume');self.state('playing')
    def test_pause_during_conversion_and_latest_seek_win(self):
        entered,release=threading.Event(),threading.Event();original=self.bridge.convert
        def slow(*args):entered.set();release.wait(5);return original(*args)
        with patch.object(self.bridge,'convert',side_effect=slow):
            self.command('play');self.assertTrue(entered.wait(3))
            self.command('seek',targetMs=8000);self.command('seek',targetMs=2000);self.command('pause');release.set()
            self.state('paused');self.assertEqual(self.bridge.status()['native']['sample'],88200)
        self.command('resume');self.state('playing')
    def test_stop_during_conversion_never_starts_sender(self):
        entered,release=threading.Event(),threading.Event();original=self.bridge.convert
        def slow(*args):entered.set();release.wait(5);return original(*args)
        with patch.object(self.bridge,'convert',side_effect=slow):
            self.command('play');self.assertTrue(entered.wait(3));self.command('stop');release.set()
            time.sleep(.25);self.assertIsNone(self.bridge.state.active)
    def test_stale_controls_and_invalid_input(self):
        self.command('play')
        result=self.bridge.command(dict(action='stop',session='test',sequence=1))
        self.assertFalse(result['accepted']);self.assertEqual(self.bridge.state.desired,'playing')
        for target in [-1,float('nan'),float('inf'),'100',None]:
            with self.assertRaises(ValueError):self.command('seek',targetMs=target)
        with self.assertRaises(ValueError):self.command('clock')
    def test_converter_failure_reported_and_next_play_recovers(self):
        original=self.bridge.kss2vgm;self.bridge.kss2vgm=self.path/'missing.exe'
        self.command('play');wait(lambda:self.bridge.status()['error']);self.assertIsNone(self.bridge.state.active)
        self.bridge.kss2vgm=original;self.command('play');self.state('playing')
    def test_recompile_during_preparation_uses_only_new_media(self):
        entered,release=threading.Event(),threading.Event();original=self.bridge.convert
        def slow(*args):entered.set();release.wait(5);return original(*args)
        with patch.object(self.bridge,'convert',side_effect=slow):
            self.command('play');self.assertTrue(entered.wait(3));self.command('stop');r=self.command('play')
            self.command('pause');release.set();self.state('paused',r['generation'])
        starts=[x for x in rows(self.bridge.log_path) if x['kind']=='sender-start']
        self.assertEqual(len(starts),1);self.assertEqual(starts[0]['generation'],r['generation'])
    def test_seek_beyond_cached_trace_extends_conversion(self):
        self.command('play');self.state('playing')
        self.command('seek',targetMs=21075);self.state('playing')
        self.assertGreater(self.bridge.state.media['summary']['samples'],21075*44.1)
    def test_shutdown_while_playing_mutes_and_closes(self):
        self.command('play');self.state('playing');self.bridge.close()
        self.assertFalse(self.bridge.worker.is_alive())
        sent=[bytes.fromhex(x['hex'])[::32] for x in rows(self.path/'writes.jsonl')]
        self.assertIn(frame(0x17,8,0),sent[-1])
if __name__=='__main__':unittest.main(verbosity=2)

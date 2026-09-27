import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from test_control import ROOT, SENDER, FIX, frame, rows, wait, native_status, module
from terminal_fade import ending_plan

class Plan(unittest.TestCase):
    def test_actual_contrail_browser_end_at_44100_and_48000(self):
        for rate in [44100,48000]:
            plan=ending_plan(dict(sampleRate=rate,fadeDurationMs=5000,bufferedMs=165000,isFaded=True))
            self.assertEqual(plan['start_sample'],159*44100)
            self.assertAlmostEqual(plan['end_sample']/44100,164,delta=.001)
    def test_duration_is_read_from_metadata_not_fixed(self):
        plan=ending_plan(dict(sampleRate=44100,fadeDurationMs=2000,bufferedMs=10000,isFaded=True))
        self.assertEqual(plan['start_sample'],7*44100)
        self.assertAlmostEqual(plan['end_sample']/44100,9,delta=.001)
    def test_no_fade_or_zero_duration_has_no_attenuation(self):
        for dur,faded in [(0,True),(5000,False)]:
            p=ending_plan(dict(sampleRate=44100,fadeDurationMs=dur,bufferedMs=10000,isFaded=faded))
            self.assertEqual(p['step'],0);self.assertEqual(p['end_sample'],441000)
    def test_invalid_metadata_rejected(self):
        for field,value in [('sampleRate',0),('fadeDurationMs',-1),('bufferedMs',float('nan')),('isFaded','true')]:
            request=dict(sampleRate=44100,fadeDurationMs=5000,bufferedMs=165000,isFaded=True);request[field]=value
            with self.assertRaises(ValueError):ending_plan(request)

def decode(raw):
    data=bytes.fromhex(raw['hex'])[::32];writes=[];i=0
    while i+4<len(data):
        if data[i]&0xe0==0x20 and data[i]!=0x20:
            writes.append((data[i]&31,(data[i+1]<<4)|(data[i+2]&15),(data[i+3]<<4)|(data[i+4]&15)));i+=5
        else:i+=1
    return writes

class HardwareFade(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name);self.ps=[]
    def tearDown(self):
        for p in self.ps:
            if p.poll() is None:p.kill()
            p.communicate(timeout=3)
        self.temp.cleanup()
    def start(self,name='a',rhythm=False,envelope=False,fail=0):
        status=self.path/f'{name}.status.json';control=self.path/f'{name}.control';log=self.path/f'{name}.writes'
        module.Bridge.write_control(control,'run')
        pre=frame(0x17,8,0)+frame(1,0x30,0x1f)+frame(4,0xaa,0)+frame(4,0,0x7f)
        music=frame(0x17,11,255)+frame(0x17,12,255)+frame(0x17,13,0xb)
        music+=frame(0x17,8,16 if envelope else 15)+frame(1,0x0e,0x3f if rhythm else 0)
        music+=b''.join(frame(1,a,0x10) for a in range(0x30,0x39))+frame(1,0x20,0x15)
        music+=b''.join(frame(4,a,15) for a in range(0xaa,0xaf))+frame(4,0xaf,31)
        batch=[dict(bin=-1,sample=0,hex=pre.hex()),dict(bin=0,sample=0,hex=music.hex()),dict(bin=1,sample=44100,hex='')]
        path=self.path/f'{name}.batch';path.write_text('\n'.join(json.dumps(x,separators=(',',':')) for x in batch))
        # Short tests use the same integer PCM envelope, not a runtime timing option.
        plan=dict(start_sample=8820,end_sample=26461,rate=44100,step=(1<<31)//17640)
        module.Bridge.write_control(status.with_suffix('.ending.json'),json.dumps(plan,separators=(',',':')))
        env=dict(os.environ,FAKE_LOG=str(log),FAKE_SHORT_AT=str(fail))
        p=subprocess.Popen([str(SENDER),'FT232H','play',str(path),str(control),str(status)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.ps.append(p);return p,status,control,log
    def test_natural_end_monotonic_three_chips_silent_finish(self):
        p,status,control,log=self.start();out,err=p.communicate(timeout=4)
        self.assertEqual(p.returncode,0,err);self.assertIn(b'fade-start',out);self.assertIn(b'fade-complete',out)
        sent=rows(log);events=[item for row in sent for item in decode(row)]
        psg=[d for t,a,d in events if t==0x17 and a==8];psg=psg[psg.index(15):]
        scc=[d for t,a,d in events if t==4 and a==0xaa];scc=scc[scc.index(15):]
        for address in range(0xaa,0xaf):
            levels=[d for t,a,d in events if t==4 and a==address]
            levels=levels[levels.index(15):]
            self.assertEqual(levels,sorted(levels,reverse=True))
            self.assertEqual(levels[-1],0)
            self.assertGreater(len(set(levels)),5)
        opll=[d&15 for t,a,d in events if t==1 and a==0x30];opll=opll[opll.index(0):]
        for levels in [psg,scc]:self.assertEqual(levels,sorted(levels,reverse=True));self.assertEqual(levels[-1],0);self.assertGreater(len(set(levels)),5)
        self.assertEqual(opll,sorted(opll));self.assertEqual(opll[-1],15)
        self.assertTrue(all(d>>4==1 for t,a,d in events if t==1 and a==0x30 and d!=0xff))
        fade_start=next(i for i,row in enumerate(sent) if any(t==0x17 and a==8 and 0<d<15 for t,a,d in decode(row)))
        for row in sent[fade_start:-2]:
            for t,a,d in decode(row):
                self.assertTrue((t==0x17 and a in (8,9,10)) or (t==1 and 0x30<=a<=0x38) or (t==4 and 0xaa<=a<=0xae))
        final=decode(sent[-1]);self.assertIn((1,0x20,0),final);self.assertIn((4,0xaf,0),final)
        self.assertEqual(native_status(status)['state'],'stopped')
    def test_opll_rhythm_both_nibbles_fade_without_keyoff_or_patch_change(self):
        p,_,_,log=self.start(rhythm=True);p.communicate(timeout=4)
        events=[x for row in rows(log) for x in decode(row)]
        for address in [0x37,0x38]:
            values=[d for t,a,d in events if t==1 and a==address];values=values[values.index(0x10):]
            self.assertEqual([d>>4 for d in values],sorted(d>>4 for d in values));self.assertEqual(values[-1],255)
        keys=[d for t,a,d in events if t==1 and a==0x20]
        self.assertEqual(keys[keys.index(0x15):],[0x15,0])
    def test_envelope_psg_attenuates_instead_of_leaving_bit16_enabled(self):
        p,_,_,log=self.start(envelope=True);p.communicate(timeout=4)
        levels=[d for row in rows(log) for t,a,d in decode(row) if t==0x17 and a==8]
        tail=levels[levels.index(16)+1:];self.assertTrue(all(d<16 for d in tail));self.assertEqual(tail[-1],0)
    def test_pause_does_not_start_fade_and_resume_retains_position(self):
        p,status,control,log=self.start();wait(lambda:native_status(status).get('state')=='playing')
        module.Bridge.write_control(control,'pause');wait(lambda:native_status(status).get('state')=='paused')
        before=len(rows(log));time.sleep(.5);self.assertEqual(len(rows(log)),before)
        module.Bridge.write_control(control,'run');out,_=p.communicate(timeout=4)
        self.assertIn(b'fade-complete',out)
    def test_operation_stop_and_error_do_not_execute_natural_fade(self):
        p,status,control,log=self.start();wait(lambda:native_status(status).get('state')=='playing')
        module.Bridge.write_control(control,'stop');out,_=p.communicate(timeout=3)
        self.assertNotIn(b'fade-start',out);self.assertNotIn(b'fade-complete',out)
        p,_,_,_=self.start('error',fail=3);out,_=p.communicate(timeout=3)
        self.assertNotEqual(p.returncode,0);self.assertNotIn(b'fade-start',out)
    def test_pause_and_stop_during_fade_use_immediate_mute(self):
        p,status,control,log=self.start();wait(lambda:native_status(status).get('state')=='fading')
        module.Bridge.write_control(control,'pause');wait(lambda:native_status(status).get('state')=='paused')
        self.assertIn((0x17,8,0),decode(rows(log)[-1]))
        module.Bridge.write_control(control,'stop');out,_=p.communicate(timeout=3)
        self.assertNotIn(b'fade-complete',out)
    def test_next_play_starts_with_original_volume(self):
        p,_,_,_=self.start();p.communicate(timeout=4)
        p,status,control,log=self.start('next');wait(lambda:native_status(status).get('state')=='playing')
        events=[x for row in rows(log) for x in decode(row)]
        self.assertIn((0x17,8,15),events);self.assertIn((1,0x30,0x10),events);self.assertIn((4,0xaa,15),events)
        module.Bridge.write_control(control,'stop');p.communicate(timeout=3)

if __name__=='__main__':unittest.main(verbosity=2)

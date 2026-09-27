"""Preserve music timestamps without browser synchronization or chip offsets."""
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from test_control import build, rows, FIX, SENDER, module
from encoder import register_writes
from vsif_decode import decode_batches

class MusicTiming(unittest.TestCase):
    def test_native_real_score_throughput_and_all_register_writes(self):
        writes=[x for x in rows(FIX/'writes.jsonl') if x.get('kind')=='write']
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);batch=root/'batch';control=root/'control';status=root/'state.json';log=root/'log'
            data=build(writes,batch,total_samples=441000)
            module.Bridge.write_control(control,'run')
            start=time.monotonic()
            p=subprocess.run([str(SENDER),'FT232H','play',str(batch),str(control),str(status)],
                             env=dict(os.environ,FAKE_LOG=str(log)),capture_output=True,timeout=14)
            elapsed=time.monotonic()-start
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertGreater(elapsed,10.4)
            self.assertLess(elapsed,12)
            # Exclude initial safety mute and final mute, retaining prelude/music.
            actual=[w for b in decode_batches(rows(log)[1:-1],32) for w in b]
            expected=[w for b in decode_batches(data) for w in b]
            self.assertEqual(actual,expected)

    def test_real_data_keeps_each_timestamp_and_chip_order_after_play_and_seek(self):
        writes=[x for x in rows(FIX/'writes.jsonl') if x.get('kind')=='write']
        with tempfile.TemporaryDirectory() as t:
            for target_ms in (0,2431):
                target=round(target_ms*44.1)
                data=build(writes,Path(t)/'batch',target_ms,441000)
                music=[r for r in data if r.get('bin',-1)>=0 and r['hex']]
                # Decode all rows so a compressed continuation retains its cursor.
                decoded=decode_batches(data)
                actual=[(r['sample'],w) for r,b in zip(data,decoded)
                        if r.get('bin',-1)>=0 for w in b if w[0]!=3]
                start=target if target else data[0]['prelude_before_sample']
                expected=[(s,w) for s,w in register_writes(writes) if s>=start]
                self.assertEqual(actual,expected)
                self.assertEqual([r['sample'] for r in music],sorted(set(s for s,w in expected)))

    def test_nearby_wave_changes_and_psg_attack_not_collapsed(self):
        writes=[dict(chip=c,sample=s,address=a,data=d) for c,s,a,d in
                [('PSG',0,8,15),('SCC',4410,0,10),('PSG',4630,8,12),('SCC',4851,0,20)]]
        with tempfile.TemporaryDirectory() as t:
            for target in (0,50):
                data=build(writes,Path(t)/'batch',target,8820)
                self.assertEqual([r['sample'] for r in data if r.get('bin',-1)>=0 and r['hex']],
                                 [s for s in (0,4410,4630,4851) if s>=target*44.1])

    def test_simultaneous_chip_writes_keep_source_order_in_one_batch(self):
        writes=[dict(chip=c,sample=4410,address=a,data=d) for c,a,d in
                [('YM2413',0x20,16),('PSG',8,15),('SCC',0x204,15),('SCC',0x300,16)]]
        with tempfile.TemporaryDirectory() as t:
            data=build(writes,Path(t)/'batch',total_samples=8820)
            self.assertEqual(len([r for r in data if r.get('bin',-1)>=0 and r['hex']]),1)
            events=[x for b in decode_batches(data) for x in b if x[0]!=3]
            self.assertEqual(events,[(1,0x20,16),(0x17,8,15),(4,0xae,15),(4,0xaf,16)])

    def test_native_sends_live_wave_update_at_its_own_time(self):
        writes=[dict(chip=c,sample=s,address=a,data=d) for c,s,a,d in
                [('PSG',0,8,15),('SCC',4410,0,10),('SCC',4851,0,20),('PSG',5292,8,12)]]
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);batch=root/'batch';control=root/'control';status=root/'state.json';log=root/'log'
            build(writes,batch,total_samples=8820)
            module.Bridge.write_control(control,'run')
            p=subprocess.run([str(SENDER),'FT232H','play',str(batch),str(control),str(status)],
                             env=dict(os.environ,FAKE_LOG=str(log)),capture_output=True,timeout=5)
            self.assertEqual(p.returncode,0,p.stderr)
            sent=rows(log);events=decode_batches(sent,32)
            at={w:r['at'] for r,b in zip(sent,events) for w in b}
            # Loose upper bound allows scheduler jitter; old 20ms collapse fails.
            self.assertGreaterEqual(at[4,0,20]-at[4,0,10],.006)
            self.assertLess(at[4,0,20]-at[4,0,10],.06)
            self.assertGreaterEqual(at[0x17,8,12]-at[4,0,20],.006)

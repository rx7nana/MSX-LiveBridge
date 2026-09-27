import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_control import build, frame, rows, FIX, SENDER, module, wait, native_status
from vsif_decode import decode_batches

def source(sample, address, data):
    return dict(chip='SCC', sample=sample, address=address, data=data)

def score():
    # Ch4 remains silent. Only ch5 is keyed on, at its own frequency.
    wave=[source(0,0x60+i,(i*17)&255) for i in range(32)]
    return wave+[source(0,0x108,80),source(0,0x109,1),source(0,0x204,15),source(0,0x300,16),
                 source(44100,0x60,0x55)]

def state(batches):
    return {(t,a):d for batch in decode_batches(batches) for t,a,d in batch}

class SCCWaveform(unittest.TestCase):
    def test_initial_ch5_has_wave_pitch_volume_enable(self):
        with tempfile.TemporaryDirectory() as t:
            data=build(score(),Path(t)/'batch',total_samples=88200)
            regs=state(data[:-2])
            self.assertEqual([regs[4,a] for a in range(0x80,0xa0)],[(i*17)&255 for i in range(32)])
            self.assertEqual([regs[4,a] for a in (0xa8,0xa9,0xae,0xaf)],[80,1,15,16])

    def test_live_wave_update_and_seek_boundary(self):
        with tempfile.TemporaryDirectory() as t:
            for target in (0,500,1000,1500,500):
                data=build(score(),Path(t)/'batch',target,88200)
                if target:
                    regs=state(data[:3])
                    self.assertEqual(regs[4,0x80],0x55 if target>1000 else 0)
                    self.assertEqual(regs[4,0x80],regs[4,0x60])
                regs=state(data)
                self.assertEqual(regs[4,0x80],0x55)
                self.assertEqual(regs[4,0x80],regs[4,0x60])

    def test_only_shared_wave_region_is_duplicated(self):
        from encoder import register_writes
        for address in [0,0x5f,0x80,0x9f,0x100,0x160,0x204,0x300]:
            self.assertEqual(len(list(register_writes([source(0,address,7)]))),1)
        for address in range(0x60,0x80):
            self.assertEqual(list(register_writes([source(123,address,7)])),
                             [(123,(4,address,7)),(123,(4,address+32,7))])

    def test_real_fixture_missing_ch5_wave_reproduced_and_repaired(self):
        writes=[x for x in rows(FIX/'writes.jsonl') if x.get('kind')=='write']
        shared=[x for x in writes if x['chip']=='SCC' and 0x60<=x['address']<0x80]
        self.assertTrue(shared)
        before=state(rows(FIX/'baseline-initial.jsonl'))
        self.assertFalse(any((4,a) in before for a in range(0x80,0xa0)))
        with tempfile.TemporaryDirectory() as t:
            after=state(build(writes,Path(t)/'batch'))
        self.assertEqual([after[4,a] for a in range(0x80,0xa0)],
                         [after[4,a] for a in range(0x60,0x80)])

    def test_native_pause_resume_and_paused_seek_restore_ch5_before_gate(self):
        for target in (0,500,1500):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as t:
                pth=Path(t);batch=pth/'batch';control=pth/'control';status=pth/'status.json';log=pth/'log'
                build(score(),batch,target,176400)
                module.Bridge.write_control(control,'pause' if target else 'run')
                p=subprocess.Popen([str(SENDER),'FT232H','play',str(batch),str(control),str(status)],
                                   env=dict(os.environ,FAKE_LOG=str(log)),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                try:
                    wait(lambda:native_status(status).get('state')==('paused' if target else 'playing'))
                    if not target:
                        module.Bridge.write_control(control,'pause')
                        wait(lambda:native_status(status).get('state')=='paused')
                    first=len(rows(log))
                    module.Bridge.write_control(control,'run')
                    wait(lambda:native_status(status).get('state')=='playing')
                    events=[x for b in decode_batches(rows(log)[first:],32) for x in b]
                    expected=0x55 if target>1000 else 0
                    self.assertIn((4,0x80,expected),events)
                    self.assertIn((4,0x9f,(31*17)&255),events)
                    self.assertLess(events.index((4,0x80,expected)),events.index((4,0xaf,16)))
                    self.assertIn((4,0xae,15),events)
                    module.Bridge.write_control(control,'stop')
                    out,err=p.communicate(timeout=4)
                    self.assertEqual(p.returncode,0,err)
                    self.assertIn(frame(4,0xae,0),bytes.fromhex(rows(log)[-1]['hex'])[::32])
                finally:
                    if p.poll() is None:p.kill()
                    p.communicate(timeout=4)

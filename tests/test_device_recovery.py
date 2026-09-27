import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from test_control import SENDER, frame, rows, wait
import test_product as product
DEVICE=product.DEVICE
import devices

class Detection(unittest.TestCase):
    def test_opened_device_with_hidden_identity_is_busy_not_missing(self):
        for device in [devices.Device('','Other','',True,0),devices.Device('TEST123','FT232H','test',True,19)]:
            with self.assertRaises(devices.DeviceBusyError):
                devices.select_device([device],devices.validate_settings({}))
        with self.assertRaises(LookupError) as error:
            devices.select_device([],devices.validate_settings({}))
        self.assertNotIsInstance(error.exception,devices.DeviceBusyError)

    def test_detail_failure_is_not_silently_reported_as_empty_list(self):
        class DLL:
            def FT_CreateDeviceInfoList(self,count):count._obj.value=1;return 0
            def FT_GetDeviceInfoDetail(self,*args):return 4
        with patch.object(ctypes,'WinDLL',return_value=DLL()):
            with self.assertRaisesRegex(OSError,'D2XX 4'):devices.enumerate_devices()

    def test_enumeration_transactions_cannot_overlap(self):
        active=0;peak=0
        def read():
            nonlocal active,peak
            active+=1;peak=max(peak,active);time.sleep(.03);active-=1;return []
        with patch.object(devices,'_enumerate_devices',side_effect=read):
            threads=[threading.Thread(target=devices.enumerate_devices) for _ in range(4)]
            for t in threads:t.start()
            for t in threads:t.join(2)
        self.assertEqual(peak,1)

# Reuse lifecycle helpers without inheriting/rerunning the original test suite.
class Recovery(unittest.TestCase):
    setUp=product.Product.setUp
    tearDown=product.Product.tearDown
    request=product.Product.request
    command=product.Product.command

    def test_busy_then_reconnect_recovers_without_application_restart(self):
        self.service.enumerator=lambda:[devices.Device('','Other','',True,0)]
        wait(lambda:self.service.state()=='FTDIは使用中です',3)
        result=self.command('play');self.assertFalse(result['accepted']);self.assertEqual(result['reason'],'device busy')
        self.assertIsNone(self.service.engine.state.active)
        self.service.enumerator=lambda:[DEVICE]
        wait(lambda:self.service.state()=='msxplay待機中',3)
        self.assertTrue(self.command('play')['accepted'])
        wait(lambda:self.service.state()=='再生中',20)

    def test_detection_failure_has_distinct_status_and_recovers(self):
        def fail():raise OSError('D2XX test failure')
        self.service.enumerator=fail
        wait(lambda:self.service.state()=='FTDI検出エラー',3)
        self.service.enumerator=lambda:[DEVICE]
        wait(lambda:self.service.state()=='msxplay待機中',3)

class OwnerFallback(unittest.TestCase):
    def test_owner_exit_ends_sender_even_if_driver_write_never_returns(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);batch=root/'batch';control=root/'control';status=root/'state';life=root/'life'
            batch.write_text('{"bin":-1,"sample":0,"hex":""}\n{"bin":0,"sample":44100,"hex":""}\n')
            control.write_text('run\n')
            owner=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
            sender=None
            try:
                sender=subprocess.Popen([str(SENDER),'FT232H','play',str(batch),str(control),str(status),'--owner',str(owner.pid)],
                    env=dict(os.environ,FAKE_WRITE_MS='30000',FAKE_LOG=str(root/'log'),FAKE_LIFECYCLE=str(life)),
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                wait(lambda:life.exists())
                owner.terminate();owner.wait(timeout=3)
                sender.communicate(timeout=8)
                self.assertEqual(sender.returncode,11)
            finally:
                for p in [sender,owner]:
                    if p and p.poll() is None:p.kill()
                    if p:p.communicate(timeout=3)

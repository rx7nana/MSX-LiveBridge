import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from test_control import ROOT, FIX, SENDER, CONVERTER, wait, rows, frame, fixture_bytes, native_status
from devices import Device, select_device, validate_settings
from service import Service
from identity import EXTENSION_ID, ALLOWED_EXTENSION_IDS, ALLOWED_EXTENSION_ORIGINS
from processes import ConverterJob

DEVICE=Device('TEST123','FT232H','Test VSIF')

class Devices(unittest.TestCase):
    def test_blank_serial_uses_usb_location(self):
        d=Device('','FT232H','Single RS232-HS',location=19)
        self.assertEqual(select_device([d],validate_settings({}))[1:],('FT232H',240000,32,True))
        self.assertEqual(d.identifier,'@00000013')
    def test_multiple_blank_serials_require_explicit_location(self):
        a=Device('','FT232H','same',location=19);b=Device('','FT232H','same',location=20)
        with self.assertRaises(LookupError):select_device([a,b],validate_settings({}))
        self.assertEqual(select_device([a,b],validate_settings({'serial':b.identifier}))[0],b)
        with self.assertRaises(LookupError):select_device([Device('','FT232H','unknown')],validate_settings({}))
    def test_auto_h_and_r_keep_verified_distinction(self):
        for kind,width,verified in [('FT232H',32,True),('FT232R',25,False)]:
            d=Device('TEST123',kind,'test')
            result=select_device([d],validate_settings({}))
            self.assertEqual(result[1:],(kind,240000,width,verified))
    def test_ambiguous_unknown_missing_fail_closed(self):
        for devices in [[],[DEVICE,Device('OTHER','FT232H','test')],[Device('X','Other','test')]]:
            with self.assertRaises(LookupError):select_device(devices,validate_settings({}))
    def test_serial_selection_and_custom_validation(self):
        settings=validate_settings(dict(profile='Custom',serial='TEST123',baud=480000,width=17))
        self.assertEqual(select_device([DEVICE,Device('OTHER','FT232H','test')],settings)[1:],('Custom',480000,17,False))
        for key,value in [('baud',0),('width',256),('profile','bad'),('baud',True),('serial','x'*16)]:
            with self.assertRaises(ValueError):validate_settings({key:value})

class Product(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'app';self.seq=0
        self.env=patch.dict(os.environ,FAKE_LOG=str(Path(self.temp.name)/'writes'),FAKE_LIFECYCLE=str(Path(self.temp.name)/'lifecycle'))
        self.env.start();self.service=Service(self.root,CONVERTER,SENDER,enumerator=lambda:[DEVICE],port=0)
        wait(lambda:not self.service.searching)
    def tearDown(self):
        self.service.close();self.env.stop();self.temp.cleanup()
    def request(self,path='/command',value=None,token=None,origin=None,host=None):
        headers={'Authorization':'Bearer '+(token or self.service.token),'Content-Type':'application/json'}
        if origin:headers['Origin']=origin
        if host:headers['Host']=host
        req=urllib.request.Request(f'http://127.0.0.1:{self.service.port}'+path,
            data=json.dumps(value).encode() if value is not None else None,headers=headers)
        with urllib.request.urlopen(req,timeout=4) as response:return json.load(response)
    def command(self,action,**extra):
        self.seq+=1
        if action=='play':
            data=fixture_bytes('contrail.mgs');extra.update(mgs=base64.b64encode(data).decode(),sha256=hashlib.sha256(data).hexdigest(),durationMs=10000)
        return self.request(value=dict(action=action,session='product',sequence=self.seq,**extra))
    def test_authenticated_session_denies_web_origins_wrong_token_and_rebinding(self):
        result=self.request('/session');self.assertEqual(result['app'],'MSX LiveBridge');self.assertNotIn('token',result)
        for extra in [dict(token='wrong'),dict(origin='https://msxplay.com'),dict(origin='https://evil.example'),dict(host='evil.example')]:
            with self.assertRaises(urllib.error.HTTPError) as err:self.request('/session',**extra)
            self.assertEqual(err.exception.code,403)
        self.assertEqual(self.request('/session',origin=f'chrome-extension://{EXTENSION_ID}')['instance'],self.service.instance)
        with self.assertRaises(urllib.error.HTTPError):self.request('/control',value={'action':'stop'})
    def test_store_and_unpacked_authenticate_commands_but_never_bypass_token(self):
        for origin in ALLOWED_EXTENSION_ORIGINS:
            with self.subTest(origin=origin), patch.object(self.service,'command',return_value={'accepted':True}) as command:
                self.assertEqual(self.request('/session',origin=origin)['instance'],self.service.instance)
                self.assertTrue(self.request(value={'action':'pause'},origin=origin)['accepted'])
                command.assert_called_once_with({'action':'pause'})
                command.reset_mock()
                for path,value in [('/session',None),('/command',{'action':'pause'})]:
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        self.request(path,value=value,origin=origin,token='wrong')
                    self.assertEqual(error.exception.code,403)
                command.assert_not_called()
    def test_unknown_and_lookalike_origins_are_denied(self):
        for origin in [*ALLOWED_EXTENSION_ORIGINS,'chrome-extension://'+'a'*32]:
            for bad in ([origin] if origin not in ALLOWED_EXTENSION_ORIGINS else [origin+'.evil',origin+'/',origin.upper()]):
                with self.subTest(origin=bad), self.assertRaises(urllib.error.HTTPError) as error:
                    self.request('/session',origin=bad)
                self.assertEqual(error.exception.code,403)
    def test_full_lifecycle_play_pause_close_mutes_removes_credentials_and_children(self):
        self.assertEqual(self.service.state(),'msxplay待機中');self.command('play')
        wait(lambda:self.service.state()=='再生中',20)
        self.command('pause');wait(lambda:self.service.engine.status()['native']['state']=='paused')
        self.assertEqual(self.service.state(),'一時停止中');self.command('resume');wait(lambda:self.service.state()=='再生中')
        process=self.service.engine.state.active[0];port=self.service.port
        self.service.close();self.assertIsNotNone(process.poll());self.assertFalse((self.root/'session.json').exists())
        self.assertFalse(self.service.engine.worker.is_alive());self.assertFalse(self.service.http_thread.is_alive())
        sent=[bytes.fromhex(x['hex'])[::32] for x in rows(Path(self.temp.name)/'writes')]
        self.assertIn(frame(0x17,8,0),sent[-1]);self.assertIn(frame(4,0xaf,0),sent[-1])
        with self.assertRaises(urllib.error.URLError):self.request('/session')
    def test_profile_change_stops_before_next_play_and_persists(self):
        self.command('play');wait(lambda:self.service.state()=='再生中',20)
        old=self.service.engine.state.active[0]
        self.service.configure(dict(profile='FT232R',serial='',baud=240000,width=32))
        wait(lambda:old.poll() is not None)
        self.assertEqual(self.service.state(),'VSIFが見つかりません')
        self.assertEqual(json.loads((self.root/'settings.json').read_text())['profile'],'FT232R')
    def test_recompile_works_when_driver_hides_owned_device(self):
        def enumeration():
            active=self.service.engine.state.active
            return [] if active and active[0].poll() is None else [DEVICE]
        self.service.enumerator=enumeration
        self.command('play');wait(lambda:self.service.state()=='再生中',20)
        old=self.service.engine.state.active[0]
        time.sleep(1.1)
        self.assertTrue(self.command('play')['accepted'])
        wait(lambda:self.service.engine.state.active and self.service.engine.state.active[0] is not old and self.service.state()=='再生中',20)
        self.assertIsNotNone(old.poll())
    def test_no_device_never_opens_sender(self):
        self.service.devices=[]
        self.assertFalse(self.command('play')['accepted']);self.assertIsNone(self.service.engine.state.active)
    def test_blank_serial_end_to_end_uses_location_and_stops(self):
        self.service.enumerator=lambda:[Device('','FT232H','Single RS232-HS',location=19)]
        self.service.devices=self.service.enumerator()
        self.assertEqual(self.service.state(),'msxplay待機中')
        self.assertTrue(self.command('play')['accepted']);wait(lambda:self.service.state()=='再生中',20)
        process=self.service.engine.state.active[0]
        self.assertIn('--location',process.args);self.assertNotIn('--device',process.args)
        self.command('pause');wait(lambda:self.service.engine.status()['native']['state']=='paused')
        self.command('resume');wait(lambda:self.service.state()=='再生中')
        self.service.close();self.assertEqual(process.returncode,0)
    def test_closing_during_conversion_cancels_children(self):
        self.command('play');self.service.close();self.assertFalse(self.service.engine.worker.is_alive())
        self.assertFalse((self.root/'session.json').exists())
    def test_credentials_acl_is_protected_and_rotates(self):
        # Inherited Everyone/Users permissions must not survive on the session directory.
        from ctypes import wintypes as w
        api=ctypes.WinDLL('advapi32',use_last_error=True)
        api.GetFileSecurityW.argtypes=[w.LPCWSTR,w.DWORD,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD)]
        size=w.DWORD();api.GetFileSecurityW(str(self.root),4,None,0,ctypes.byref(size))
        descriptor=ctypes.create_string_buffer(size.value)
        self.assertTrue(api.GetFileSecurityW(str(self.root),4,descriptor,size,ctypes.byref(size)))
        control=w.WORD();revision=w.DWORD()
        self.assertTrue(api.GetSecurityDescriptorControl(descriptor,ctypes.byref(control),ctypes.byref(revision)))
        self.assertTrue(control.value & 0x1000)
        previous=self.service.token;self.service.close()
        self.service=Service(self.root,CONVERTER,SENDER,enumerator=lambda:[DEVICE],port=0)
        self.assertNotEqual(previous,self.service.token)

class Packaging(unittest.TestCase):
    def test_registered_native_host_and_native_gate_use_exact_same_two_ids(self):
        import re
        from security import register_host
        expected=['chrome-extension://'+identity+'/' for identity in ALLOWED_EXTENSION_IDS]
        self.assertEqual(len(expected),2)
        self.assertIn('chrome-extension://cfkcbmejlakciepflheboofnphdkoghf/',expected)
        self.assertEqual(re.findall(r'L"(chrome-extension://[a-p]{32}/)"',(ROOT/'native/identity.hpp').read_text()),expected)
        with tempfile.TemporaryDirectory() as temp, patch('security.winreg.CreateKeyEx'), patch('security.winreg.SetValueEx') as write:
            root=Path(temp);register_host(root,ROOT/'native/MSXLiveBridge.Connect.exe')
            self.assertEqual(json.loads((root/'native-host.json').read_text())['allowed_origins'],expected)
            self.assertEqual(write.call_count,6)
    def test_icon_small_sizes_preserved_in_png_and_ico(self):
        from PIL import Image
        raw=(ROOT/'assets/MSXLiveBridge.ico').read_bytes();count=struct.unpack_from('<H',raw,4)[0]
        entries={}
        for n in range(count):
            width,_,_,_,_,_,size,offset=struct.unpack_from('<BBBBHHII',raw,6+16*n);entries[width or 256]=raw[offset:offset+size]
        for n in [16,24,32]:
            original=Image.open(ROOT/'assets/1024.png').convert('RGBA')
            expected=original.resize((n,n),Image.Resampling.BOX)
            actual=Image.open(ROOT/f'assets/{n}.png').convert('RGBA')
            self.assertEqual(actual.tobytes(),expected.tobytes())
            self.assertEqual(entries[n],(ROOT/f'assets/{n}.png').read_bytes())
    def test_product_extension_no_manual_ui_or_wildcard_hosts(self):
        manifest=json.loads((ROOT/'config/manifest.unpacked.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['name'],'MSX LiveBridge');self.assertNotIn('action',manifest)
        self.assertEqual(manifest['host_permissions'],['http://127.0.0.1:27183/*'])
        self.assertFalse((ROOT/'extension/popup.html').exists())
        key=base64.b64decode(manifest['key']);identity=''.join(chr(97+int(c,16)) for c in hashlib.sha256(key).hexdigest()[:32])
        self.assertEqual(identity,EXTENSION_ID)
    def test_converter_dies_with_job(self):
        job=ConverterJob();p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])
        try:job.assign(p);job.close();p.wait(timeout=3)
        finally:
            if p.poll() is None:p.kill();p.wait()
    def test_native_host_rejects_other_extension_and_malformed_message(self):
        host=ROOT/'native/MSXLiveBridge.Connect.exe'
        result=subprocess.run([str(host),'chrome-extension://'+'a'*32+'/'],input=b'',capture_output=True)
        self.assertEqual(result.returncode,2);self.assertEqual(result.stdout,b'')
        for identity in ALLOWED_EXTENSION_IDS:
            origin=f'chrome-extension://{identity}/'
            result=subprocess.run([str(host),origin],input=struct.pack('<I',9000),capture_output=True)
            self.assertEqual(result.returncode,3)
            for bad in [origin.rstrip('/'),origin+'evil',origin.upper()]:
                result=subprocess.run([str(host),bad],input=b'',capture_output=True)
                self.assertEqual(result.returncode,2)

class NativeLifecycle(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.processes=[]
    def tearDown(self):
        for p in self.processes:
            if p.poll() is None:p.kill()
            p.communicate(timeout=3)
        self.temp.cleanup()
    def start(self,profile='FT232H',width=32,baud=240000,owner=None):
        from playback import Bridge
        control=self.root/'control';Bridge.write_control(control,'run')
        status=self.root/'status.json';batch=self.root/'batch';log=self.root/'writes'
        batch.write_text('\n'.join(json.dumps(row,separators=(',',':')) for row in [
            dict(bin=-1,sample=0,hex=frame(0x17,8,0).hex()),
            dict(bin=0,sample=0,hex=frame(0x17,8,15).hex()),dict(bin=1,sample=441000,hex='')]))
        args=[str(SENDER),profile,'play',str(batch),str(control),str(status),'--device','TEST123','--baud',str(baud),'--width',str(width)]
        if owner:args+=['--owner',str(owner.pid)]
        p=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env=dict(os.environ,FAKE_LOG=str(log),FAKE_BAUD=str(baud)));self.processes.append(p)
        wait(lambda:native_status(status).get('state')=='playing')
        return p,control,log
    def test_ft232r_and_custom_profile_physical_width_and_mute(self):
        from playback import Bridge
        for profile,width,baud in [('FT232R',25,240000),('Custom',17,480000)]:
            p,control,log=self.start(profile,width,baud)
            Bridge.write_control(control,'stop');p.communicate(timeout=3)
            self.assertEqual(p.returncode,0)
            for row in rows(log):
                physical=bytes.fromhex(row['hex'])
                self.assertEqual(len(physical)%width,0)
                self.assertTrue(all(len(set(physical[i:i+width]))==1 for i in range(0,len(physical),width)))
            self.assertIn(frame(0x17,8,0),bytes.fromhex(rows(log)[-1]['hex'])[::width]);log.unlink()
    def test_parent_exit_mutes_and_ends_without_control_file_change(self):
        owner=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);self.processes.append(owner)
        p,control,log=self.start(owner=owner)
        owner.terminate();owner.wait(timeout=3);p.communicate(timeout=3)
        self.assertEqual(p.returncode,0);self.assertEqual(control.read_text().strip(),'run')
        self.assertIn(frame(0x17,8,0),bytes.fromhex(rows(log)[-1]['hex'])[::32])

if __name__=='__main__':unittest.main(verbosity=2)

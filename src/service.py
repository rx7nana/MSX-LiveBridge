"""Desktop lifecycle, device selection and loopback authentication."""
import json
import hmac
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import shutil
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from identity import APP_NAME, ALLOWED_EXTENSION_ORIGINS, VERSION
from devices import enumerate_devices, select_device, validate_settings, DeviceBusyError
from playback import Bridge
from security import atomic_json, private_directory
from processes import ConverterJob

class Server(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=False
    def get_request(self):
        conn,address=super().get_request();conn.settimeout(3);return conn,address

def handler_factory(service):
    class Handler(BaseHTTPRequestHandler):
        def reply(self,code,value):
            data=json.dumps(value).encode()
            self.send_response(code)
            self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Connection','close')
            self.end_headers()
            try:self.wfile.write(data)
            except OSError:pass
        def authorized(self):
            if self.headers.get('Host') != f'127.0.0.1:{service.port}':return False
            origin=self.headers.get('Origin')
            if origin and origin not in ALLOWED_EXTENSION_ORIGINS:return False
            return hmac.compare_digest(self.headers.get('Authorization',''),f'Bearer {service.token}')
        def do_GET(self):
            if not self.authorized():self.reply(403,{'error':'denied'});return
            if self.path!='/session':self.reply(404,{});return
            self.reply(200,dict(app=APP_NAME,instance=service.instance,version=VERSION))
        def do_POST(self):
            if not self.authorized():self.reply(403,{'error':'denied'});return
            if self.path!='/command':self.reply(404,{});return
            try:
                if self.headers.get('Content-Type')!='application/json':raise ValueError('JSON required')
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=12*1024*1024:raise ValueError('request size')
                value=json.loads(self.rfile.read(size))
                if not isinstance(value,dict):raise ValueError('object required')
                result=service.command(value)
                self.reply(200,result)
            except (ValueError,TypeError,KeyError) as error:self.reply(400,{'error':str(error)})
            except Exception:
                service.logger.exception('操作を処理できませんでした。');self.reply(500,{'error':'MSX LiveBridge error'})
        def do_OPTIONS(self):self.reply(403,{'error':'denied'})
        def log_message(self,*_):pass
    return Handler

class Service:
    def __init__(self,root,converter,sender,enumerator=enumerate_devices,port=27183):
        self.root=Path(root);private_directory(self.root)
        self.lock=threading.RLock();self.closing=False;self.closed=False
        self.token=secrets.token_urlsafe(32);self.instance=secrets.token_hex(16)
        self.enumerator=enumerator;self.devices=[];self.device_error='';self.searching=True
        self.settings=validate_settings({})
        self.logger=logging.getLogger('MSXLiveBridge.'+self.instance);self.logger.setLevel(logging.INFO)
        handler=RotatingFileHandler(self.root/'diagnostics.log',maxBytes=1024*1024,backupCount=2,encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'));self.logger.addHandler(handler)
        try:self.settings=validate_settings(json.loads((self.root/'settings.json').read_text()))
        except FileNotFoundError:pass
        except (ValueError,TypeError):self.logger.warning('設定を既定値に戻しました。')
        self.run_dir=self.root/'runs'/self.instance
        self.converter_job=ConverterJob()
        self.engine=Bridge(self.run_dir,converter,165,self.token,sender,self.sender_options,self.converter_job.assign)
        try:
            self.http=Server(('127.0.0.1',port),handler_factory(self));self.port=self.http.server_port
            self.http_thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.http_thread.start()
            atomic_json(self.root/'session.json',dict(token=self.token,port=self.port,instance=self.instance))
        except Exception:
            self.engine.close();self.converter_job.close();raise
        self.stop_event=threading.Event()
        self.device_thread=threading.Thread(target=self.watch_devices,daemon=True);self.device_thread.start()
        self.logger.info('MSX LiveBridge %s 起動',VERSION)

    def watch_devices(self):
        previous=None
        while not self.stop_event.is_set():
            try:
                # Some D2XX drivers hide serials while another process owns the
                # handle. Our engine is such a process: retain its last identity.
                active=self.engine.state.active
                if not active or active[0].poll() is not None:
                    devices=self.enumerator()
                    with self.lock:
                        active=self.engine.state.active
                        if not active or active[0].poll() is not None:self.devices=devices
                        self.device_error='';self.searching=False
            except OSError as e:
                with self.lock:
                    active=self.engine.state.active
                    if not active or active[0].poll() is not None:
                        self.devices=[];self.device_error=str(e);self.searching=False
            condition=(self.device_error,tuple((d.identifier,d.model,d.busy) for d in self.devices))
            if condition!=previous:
                self.logger.info('FTDI検出状態: %s',condition)
                previous=condition
            self.stop_event.wait(1)

    def selection(self):
        # Lists/settings are replaced atomically, never mutated. Do not acquire
        # the UI lock from the playback worker while it owns its state lock.
        return select_device(self.devices,self.settings)

    def sender_options(self):
        if self.closing:raise RuntimeError('MSX LiveBridge is closing')
        # prepare() has closed the previous handle. Discover again now, rather
        # than using a possibly stale one-second UI discovery snapshot.
        self.devices=self.enumerator()
        d,profile,baud,width,_=self.selection()
        address=['--device',d.serial] if d.serial else ['--location',str(d.location)]
        return profile,[*address,'--baud',str(baud),'--width',str(width),'--owner',str(os.getpid())]

    def command(self,value):
        with self.lock:
            if self.closing:return {'accepted':False,'reason':'closing'}
            if value.get('action')=='play':
                try:self.selection()
                except DeviceBusyError:return {'accepted':False,'reason':'device busy'}
                except LookupError:return {'accepted':False,'reason':'no device'}
            return self.engine.command(value)

    def configure(self,value):
        value=validate_settings(value)
        with self.lock:
            if self.closing:return
            if value==self.settings:return
            # Device/settings changes are user stops, never a new playback algorithm.
            with self.engine.changed:
                s=self.engine.state;s.desired='stopped';s.generation+=1
                if s.active and s.active[0].poll() is None:self.engine.write_control(s.active[1],'stop')
                self.engine.changed.notify_all()
            self.settings=value;atomic_json(self.root/'settings.json',value)
            self.logger.info('FTDI設定: %s',value)

    def state(self):
        if self.closing:return '終了中'
        snapshot=self.engine.status()
        if snapshot['error']:return 'エラー'
        native=snapshot.get('native') or {}
        if snapshot['desired']!='stopped':
            if snapshot['desired']=='paused':return '一時停止中'
            if native.get('state') in ('playing','fading'):return '再生中'
            return '再生準備中'
        if self.searching:return 'VSIF検索中'
        if self.device_error:return 'FTDI検出エラー'
        try:self.selection()
        except DeviceBusyError:return 'FTDIは使用中です'
        except LookupError:return 'VSIFが見つかりません' if len(self.devices)<2 else 'エラー'
        return 'msxplay待機中'

    def close(self):
        with self.lock:
            if self.closed:return
            self.closing=True
        (self.root/'session.json').unlink(missing_ok=True)
        self.http.shutdown();self.http.server_close();self.http_thread.join(4)
        self.stop_event.set();self.device_thread.join(4)
        try:self.engine.close()
        except Exception:
            self.logger.exception('終了処理を再試行します。')
            active=self.engine.state.active
            if active and active[0].poll() is None:
                self.engine.write_control(active[1],'stop')
                try:active[0].wait(timeout=5)
                except Exception:active[0].kill();active[0].wait(timeout=3)
        self.logger.info('通信を終了しました。')
        self.converter_job.close()
        self.closed=True
        # Keep only recent diagnostics, not an unbounded history of captured music.
        runs=sorted((self.root/'runs').iterdir(),key=lambda p:p.stat().st_mtime,reverse=True)
        for old in runs[3:]:
            if old.is_dir() and old.resolve().parent==(self.root/'runs').resolve():shutil.rmtree(old)
        for handler in list(self.logger.handlers):handler.close();self.logger.removeHandler(handler)

"""Read-only D2XX discovery and explicit transmission settings."""
import ctypes
from ctypes import wintypes as w
from dataclasses import dataclass
from threading import Lock

_enumeration_lock = Lock()

class DeviceBusyError(LookupError):
    pass

PROFILES = {'FT232H': (240000, 32, True), 'FT232R': (240000, 25, False)}

@dataclass(frozen=True)
class Device:
    serial: str
    model: str
    description: str
    busy: bool = False
    location: int = 0

    @property
    def identifier(self):
        return self.serial or (f'@{self.location:08x}' if self.location else '')

    @property
    def label(self):
        return self.serial or f'USB位置 {self.location:08X}（番号なし）'

def enumerate_devices():
    # D2XX keeps a process-wide device list between Create and GetDetail.
    with _enumeration_lock:
        return _enumerate_devices()

def _enumerate_devices():
    dll = ctypes.WinDLL('ftd2xx.dll', winmode=0x800)  # installed system driver only
    count = w.DWORD()
    if dll.FT_CreateDeviceInfoList(ctypes.byref(count)):
        raise OSError('FTDIデバイス一覧を取得できません。')
    result = []
    for i in range(min(count.value, 256)):
        flags, kind, ident, location = (w.DWORD() for _ in range(4))
        serial, description, handle = ctypes.create_string_buffer(16), ctypes.create_string_buffer(64), w.HANDLE()
        error = dll.FT_GetDeviceInfoDetail(w.DWORD(i), ctypes.byref(flags), ctypes.byref(kind),
            ctypes.byref(ident), ctypes.byref(location), serial, description, ctypes.byref(handle))
        if error: raise OSError(f'FTDIデバイス情報を取得できません（D2XX {error}）。')
        result.append(Device(serial.value.decode('ascii', 'replace'),
            {8:'FT232H',5:'FT232R'}.get(kind.value, 'Other'),
            description.value.decode('ascii','replace'), bool(flags.value & 1), location.value))
    return result

def validate_settings(value):
    profile = value.get('profile', '自動')
    if profile not in ('自動','FT232H','FT232R','Custom'): raise ValueError('FTDIの選択が不正です。')
    baud, width = value.get('baud',240000), value.get('width',32)
    if type(baud) is not int or not 300 <= baud <= 3000000: raise ValueError('baud rateは300〜3000000で指定してください。')
    if type(width) is not int or not 1 <= width <= 255: raise ValueError('clock幅は1〜255で指定してください。')
    serial = value.get('serial','')
    if not isinstance(serial,str) or len(serial)>15 or any(ord(c)<32 or ord(c)>126 for c in serial):
        raise ValueError('デバイス識別番号が不正です。')
    return dict(profile=profile,baud=baud,width=width,serial=serial)

def select_device(devices, settings):
    profile, serial = settings['profile'], settings['serial']
    candidates = [d for d in devices if d.identifier and (not serial or d.identifier==serial)
        and (profile=='Custom' or d.model in PROFILES)
        and (profile in ('自動','Custom') or d.model==profile)]
    if not candidates:
        # An opened D2XX device can have blank identity/type/location fields.
        # Never turn that positive "opened" flag into a claim of disconnection.
        if any(d.busy and (not d.identifier or not serial or d.identifier==serial) for d in devices):
            raise DeviceBusyError('FTDIは使用中です。使用中のアプリを終了してください。残る場合はUSBを挿し直してください。')
        raise LookupError('VSIFが見つかりません')
    if len(candidates)!=1: raise LookupError('詳細設定でデバイスを選択してください。')
    d=candidates[0]
    if d.busy:
        raise DeviceBusyError('FTDIは使用中です。使用中のアプリを終了してください。残る場合はUSBを挿し直してください。')
    selected = d.model if profile=='自動' else profile
    baud,width,verified = PROFILES[selected] if selected in PROFILES else (settings['baud'],settings['width'],False)
    return d, selected, baud, width, verified

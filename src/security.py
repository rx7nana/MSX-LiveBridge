"""Per-user authenticated discovery. Credentials never enter the web page."""
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import sys
import winreg
from identity import ALLOWED_EXTENSION_ORIGINS, HOST_NAME

def data_root():
    return Path(os.environ['LOCALAPPDATA'])/'MSXLiveBridge'

def private_directory(path):
    path.mkdir(parents=True,exist_ok=True)
    advapi=ctypes.WinDLL('advapi32',use_last_error=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE]
    kernel.LocalFree.argtypes=[ctypes.c_void_p]
    kernel.LocalFree.restype=ctypes.c_void_p
    advapi.OpenProcessToken.argtypes=[w.HANDLE,w.DWORD,ctypes.POINTER(w.HANDLE)]
    advapi.GetTokenInformation.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD)]
    token=w.HANDLE()
    if not advapi.OpenProcessToken(kernel.GetCurrentProcess(),8,ctypes.byref(token)): raise ctypes.WinError()
    try:
        size=w.DWORD()
        advapi.GetTokenInformation(token,1,None,0,ctypes.byref(size))
        buf=ctypes.create_string_buffer(size.value)
        if not advapi.GetTokenInformation(token,1,buf,size,ctypes.byref(size)): raise ctypes.WinError()
        sid=ctypes.cast(buf,ctypes.POINTER(ctypes.c_void_p))[0]
        text=w.LPWSTR()
        advapi.ConvertSidToStringSidW.argtypes=[ctypes.c_void_p,ctypes.POINTER(w.LPWSTR)]
        if not advapi.ConvertSidToStringSidW(sid,ctypes.byref(text)): raise ctypes.WinError()
        try: sddl=f'D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;{text.value})'
        finally: kernel.LocalFree(ctypes.cast(text,ctypes.c_void_p))
        descriptor=ctypes.c_void_p()
        advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes=[w.LPCWSTR,w.DWORD,ctypes.POINTER(ctypes.c_void_p),ctypes.c_void_p]
        if not advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl,1,ctypes.byref(descriptor),None): raise ctypes.WinError()
        try:
            advapi.SetFileSecurityW.argtypes=[w.LPCWSTR,w.DWORD,ctypes.c_void_p]
            if not advapi.SetFileSecurityW(str(path),0x80000004,descriptor): raise ctypes.WinError()
        finally: kernel.LocalFree(descriptor)
    finally: kernel.CloseHandle(token)

def atomic_json(path, data):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=True),encoding='utf-8')
    temp.replace(path)

def register_host(root, host):
    manifest=root/'native-host.json'
    atomic_json(manifest,dict(name=HOST_NAME,description='MSX LiveBridge',path=str(host.resolve()),
        type='stdio',allowed_origins=[origin+'/' for origin in ALLOWED_EXTENSION_ORIGINS]))
    for browser in ['Google\\Chrome','Microsoft\\Edge','Chromium']:
        for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                f'Software\\{browser}\\NativeMessagingHosts\\{HOST_NAME}',0,winreg.KEY_SET_VALUE|view) as key:
                winreg.SetValueEx(key,'',0,winreg.REG_SZ,str(manifest.resolve()))

class SingleInstance:
    def __init__(self):
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.CreateMutexW.argtypes=[ctypes.c_void_p,w.BOOL,w.LPCWSTR]
        self.kernel.CreateMutexW.restype=w.HANDLE
        self.kernel.CloseHandle.argtypes=[w.HANDLE]
        self.handle=self.kernel.CreateMutexW(None,False,'Local\\MSXLiveBridge.Desktop')
        if not self.handle: raise ctypes.WinError()
        self.already_running=ctypes.get_last_error()==183
    def close(self):
        if self.handle: self.kernel.CloseHandle(self.handle);self.handle=None

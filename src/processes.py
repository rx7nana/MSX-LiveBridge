"""Kill a converter if the desktop disappears; Native handles its own mute."""
import ctypes
from ctypes import wintypes as w

class ConverterJob:
    def __init__(self):
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR]
        self.kernel.CreateJobObjectW.restype=w.HANDLE
        self.handle=self.kernel.CreateJobObjectW(None,None)
        if not self.handle:raise ctypes.WinError()
        # JOBOBJECT_EXTENDED_LIMIT_INFORMATION, 144 bytes on x64. LimitFlags
        # is at byte 16; the remaining counters/limits must be zero.
        info=ctypes.create_string_buffer(144)
        ctypes.c_uint32.from_buffer(info,16).value=0x2000
        self.kernel.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
        if not self.kernel.SetInformationJobObject(self.handle,9,info,144):raise ctypes.WinError()
        self.kernel.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
    def assign(self,process):
        if not self.kernel.AssignProcessToJobObject(self.handle,int(process._handle)):
            process.terminate();process.wait(timeout=3);raise ctypes.WinError()
    def close(self):
        if self.handle:
            self.kernel.CloseHandle.argtypes=[w.HANDLE]
            self.kernel.CloseHandle(self.handle);self.handle=None

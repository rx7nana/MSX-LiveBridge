# MSX LiveBridge 1.0.4 — Third-party notices

## MGSDRV

**MGSDRV (C) Ain./Gigamix**

Creator: Ain. / Maintainer: Gigamix. https://www.gigamix.jp/mgsdrv/

MGSDRV 3.18-derived data (8083 bytes) is embedded in kss2vgm.exe through libkss/kss-drivers. The complete byte sequence matches the upstream mgsdrv.h payload. This packaging operation does not alter it. MGSDRV.COM is not a separate bundled file. The project owner reports permission from Gigamix's Takashi Kobayashi for this existing embedded distribution form. No additional permission for other drivers is implied.

The current official MGSDRV 3.20 documentation is reproduced unmodified at licenses/MGSDR320.TXT for attribution. The embedded driver remains 3.18. Public terms: https://gigamix.hatenablog.com/entry/mgsdrv/ (embedding license and attribution section).

## Converter and embedded components

The bundled `_internal/vendor/kss2vgm.exe` is byte-identical to the official Windows kss2vgm 0.1.4 release. SHA-256: 36314759d87c41077e8cc8dcd69f174d97da688883a8e62e506b5d7b87bdeeb6.

The official binary terms prohibit commercial use and distribution for a fee. Retain those terms: **this converter-containing package is not licensed for commercial use or paid distribution**. The permissive source licenses do not remove the binary's embedded driver restrictions. MGSDRV permission does not waive other authors' conditions.

| Component | Copyright / role | License record |
|---|---|---|
| kss2vgm 0.1.4 | Copyright (c) 2016 Mitsutaka Okazaki; MGS/KSS to VGM | licenses/kss2vgm.md: ISC for source; additional binary restrictions above |
| libkss (513f355e2f54f4cbffed425ad89a658000006b3f) | Copyright (c) 2015 Mitsutaka Okazaki; MSX music playback | licenses/libkss.md: ISC; driver exception |
| emu2149 / emu2212 / emu2413 / emu76489 / emu8950 | Mitsutaka Okazaki; PSG, SCC, OPLL, SN76489, Y8950 emulation | respective licenses/emu*.txt, MIT |
| KMZ80 | Mamiya; Z80/R800 CPU emulation | licenses/kmz80.txt, PDS designation |
| KINROU5 | Copyright (C) 1996,1997 Keiichi Kuroda / BTO (MuSICA Laboratory); 5951-byte driver | upstream attribution; official converter binary conditions |
| MPK 1.03 / 1.06 | Copyright (C) K-KAZ; 7552 bytes each | upstream attribution; official converter binary conditions |
| OPX4KSS / OPLLDriver | Copyright (c) Mikasen; Copyright (c) 1989-1995 Ring.; 9260 bytes | upstream attribution; official converter binary conditions |
| mbr143 / MoonBlaster BASIC driver v1.4 | (c) Moonsoft 1992/1993 (embedded binary text); 4992 bytes | official converter binary conditions; no separate permissive grant asserted |

MGS playback uses the MGSDRV route. Other drivers remain inside the unchanged official converter; being unused by MSX LiveBridge does not mean they are absent. They are not independently relicensed under ISC/MIT or the MSX LiveBridge license. Upstream attribution is preserved in licenses/kss-drivers-attribution.md. MBM2KSS conversion code is based on Mamiya's mbm2kssx.c / mbm2kssx.h. MPK2KSS acknowledgement: Naruto.

Sources: https://github.com/digital-sound-antiques/kss2vgm/tree/0.1.4 ; https://github.com/digital-sound-antiques/libkss ; https://github.com/digital-sound-antiques/kss-drivers

## Windows runtime

| Component / bundled location | Purpose | License / notice |
|---|---|---|
| Python 3.12.14; python312.dll, base_library.zip, Python extension modules, frozen library modules | Desktop application and Bridge | PSF and incorporated licenses: licenses/Python.txt, licenses/Python-incorporated-software.txt |
| Tcl/Tk 8.6.12; tcl86t.dll, tk86t.dll, _tcl_data, _tk_data, tcl8 | Desktop GUI, dialogs, encodings and locale resources | BSD-style Tcl/Tk terms: licenses/Tcl.txt, licenses/Tk.txt; in-file notices retained |
| PyInstaller 6.22.3 bootloader and runtime hooks | Packaged EXE startup | GPL with bootloader exception, Apache-2.0 runtime hooks, MIT modules: licenses/PyInstaller-COPYING.txt; Apache text also in licenses/OpenSSL.txt |
| libffi-8.dll | ctypes calls to Windows / FTDI APIs | MIT: licenses/libffi.txt and Python incorporated notices; exact patch release not exposed by this DLL |
| OpenSSL 3.5.8, libcrypto-3-x64.dll and libssl-3-x64.dll | Python hashlib / ssl standard modules | Apache-2.0: licenses/OpenSSL.txt; Copyright OpenSSL Project Authors |
| zlib 1.3.2 (Python-linked) | ZIP / compression support | zlib license: licenses/zlib.txt |
| bzip2 1.0.8 (_bz2.pyd) | Python compression module | licenses/Python.txt contains bzip2/libbzip2 conditions |
| liblzma (_lzma.pyd) | Python compression module | Older public-domain / newer 0BSD upstream terms retained: licenses/liblzma*.txt; precise embedded version not exposed |
| libmpdec 2.5.1 (_decimal.pyd) | Python decimal module | BSD-2-Clause: Python incorporated notices |
| HACL* (Python-linked) | Hash implementations | MIT: licenses/HACL.txt |
| VCRUNTIME140.dll / VCRUNTIME140_1.dll, 14.44.35211.0 | Python runtime C/C++ support | Microsoft Distributable Code terms in licenses/Python.txt. Windows only; preserve notices, no trademark endorsement, no malicious/deceptive/unlawful use |
| Native C/C++ runtime linked into internal EXEs | Native executable support | Microsoft Visual C++ runtime; no separate Visual Studio/Build Tools installation required |

Runtime binaries are unchanged from the existing application. Python itself was not patched in this packaging operation. Only the required packaged standard-library subset is distributed. References in a third-party license to other upstream tools do not imply those tools are included.

Windows 10/11 supplies its own UCRT/API sets and system DLLs. Those OS components are not redistributed here. FTDI D2XX is loaded from the installed Windows system driver and is NOT bundled. Obtain the appropriate driver from https://ftdichip.com/drivers/d2xx-drivers/ and follow FTDI's terms.

## External software and artwork

msxplay, VSIF, MAmidiMEmo/VGMPlayer are interoperability targets or protocol references, not bundled applications. NGLOAD.COM, VGM_msx.rom, MSX-DOS/Nextor and musical data are not included; obtain them separately under their own terms. The extracted official kss2vgm executable originally came from the existing MAmidiMEmo checkout and has now been matched directly to its upstream release.

The LB artwork is the project owner's supplied 1024px original. 16/24/32px use BOX; larger sizes use Lanczos. Its license is governed by the project owner's LICENSE.txt, not by the third-party licenses above.

# Build dependencies are local and never part of the delivered application.
from pathlib import Path
import os,subprocess,sys
r=Path(__file__).parent.resolve()
assert (r/'dist').resolve().is_relative_to(r)
sys.path.insert(0,str(r/'src'))
from security import SingleInstance
guard=SingleInstance()
running=guard.already_running
guard.close()
if running:raise RuntimeError('Close MSX LiveBridge before rebuilding the distribution.')
env=os.environ.copy()
for dependency in ['native/MSXLiveBridge.Engine.exe','native/MSXLiveBridge.Connect.exe','vendor/kss2vgm.exe']:
    if not (r/dependency).is_file():raise FileNotFoundError('Prepare build dependency: '+dependency)
command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir','--name','MSXLiveBridge',
 '--distpath',str(r/'dist'),'--workpath',str(r/'build/pyinstaller'),'--specpath',str(r/'build'),
 '--version-file',str(r/'native/version.txt'),
 '--paths',str(r/'src'),'--icon',str(r/'assets/MSXLiveBridge.ico'),
 '--add-data',str(r/'assets/MSXLiveBridge.ico')+';assets',
 '--add-binary',str(r/'native/MSXLiveBridge.Engine.exe')+';native',
 '--add-binary',str(r/'native/MSXLiveBridge.Connect.exe')+';native',
 '--add-binary',str(r/'vendor/kss2vgm.exe')+';vendor',str(r/'src/app.py')]
subprocess.run(command,env=env,check=True)

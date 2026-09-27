"""Create separate store/unpacked artifacts without editing the source manifest."""
import argparse,json,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--target',choices=['store','unpacked'],required=True)
args=parser.parse_args()
source=ROOT/'extension';out=ROOT/'build'/('extension-'+args.target)
assert not out.exists(),'Output exists; choose a fresh build directory or remove the old artifact yourself'
manifest=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
assert manifest['manifest_version']==3 and manifest['version']=='1.0.4' and 'key' not in manifest
shutil.copytree(source,out)
if args.target=='unpacked':
    development=ROOT/'config/manifest.unpacked.json'
    alternate=json.loads(development.read_text(encoding='utf-8'));alternate.pop('key')
    assert alternate==manifest
    shutil.copyfile(development,out/'manifest.json')
else:
    archive=ROOT/'build'/f'MSXLiveBridge-Extension-{manifest["version"]}.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():
                info=zipfile.ZipInfo(p.relative_to(out).as_posix(),(2026,9,27,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
                z.writestr(info,p.read_bytes())
    print(archive)
print(out)

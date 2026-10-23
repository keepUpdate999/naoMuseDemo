"""Build a pinned Windows package from an allowlist; exclude all local state."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PYTHON_SHA='4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'
PYTHON_URL='https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
FILES=('desktop','business','web','vendor','real_server.py','browser_agent.py','anthropic_adapter.py',
       'secret_store.py','configure_model.py','model.example.json','requirements.lock','requirements-desktop.lock',
       'LICENSE','FLOATING_ASSISTANT.md')


def copy_source(target):
    for name in FILES:
        source=ROOT/name
        if source.is_dir():shutil.copytree(source,target/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc','source.tar'))
        else:shutil.copy2(source,target/name)


def finalize(target):
    paths=[p for p in target.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='checksums.json']
    manifest={str(p.relative_to(target)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (target/'checksums.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    package=target.with_suffix('.zip')
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for path in paths+[target/'checksums.json']:z.write(path,str(path.relative_to(target.parent)))
    print(json.dumps({'package':str(package),'sha256':hashlib.sha256(package.read_bytes()).hexdigest()}))
    return package


def build(output, archive=None):
    output.mkdir(parents=True,exist_ok=True)
    if archive is None:
        cache=ROOT/'.local/desktop-build';cache.mkdir(parents=True,exist_ok=True)
        archive=cache/'python-3.12.10-embed-amd64.zip'
        if not archive.exists():urllib.request.urlretrieve(PYTHON_URL,archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=PYTHON_SHA:raise ValueError('Python archive checksum mismatch')
    target=output/('GuDuuOS-Floating-'+time.strftime('%Y%m%d-%H%M%S'))
    target.mkdir(exist_ok=False)
    runtime=target/'runtime';runtime.mkdir()
    with zipfile.ZipFile(archive) as z:z.extractall(runtime)
    # Source and dependencies belong to this package, never a global interpreter.
    (runtime/'python312._pth').write_text('python312.zip\n.\nLib/site-packages\n..\n../vendor\nimport site\n',encoding='utf-8')
    runtime_lock=target/'requirements-runtime.lock'
    runtime_lock.write_text('\n'.join(line for line in (ROOT/'requirements.lock').read_text().splitlines()
                                     if line.strip()!='./vendor')+'\n',encoding='utf-8')
    subprocess.run(['uv','pip','install','--python',str(runtime/'python.exe'),'--target',str(runtime/'Lib/site-packages'),
                    '--no-deps','-r',str(runtime_lock),'-r',str(ROOT/'requirements-desktop.lock')],check=True)
    copy_source(target)
    (target/'Start-GuDuuOS.cmd').write_bytes(b'@echo off\r\ncd /d "%~dp0"\r\n"%~dp0runtime\\python.exe" -m desktop.launch_portable\r\nif errorlevel 1 pause\r\n')
    subprocess.run([str(runtime/'python.exe'),'-c',
        'import win32crypt,playwright,PySide6,fastapi; import real_server; from desktop.main import Assistant; print("Portable imports OK")'],cwd=target,check=True)
    # Corresponding source, upstream notices and wheel metadata/licenses travel with runtime.
    return finalize(target)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'dist');parser.add_argument('--python-archive',type=Path)
    args=parser.parse_args();build(args.output,args.python_archive)

"""Own only this Compose project; encrypted credentials and non-destructive cleanup."""
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import tarfile
import time

import httpx
from secret_store import protect, unprotect
from business.materials import PAGES

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local' / 'business'
COMPOSE = ROOT / 'business' / 'compose.yml'


def credentials():
    LOCAL.mkdir(parents=True, exist_ok=True)
    path = LOCAL / 'credentials.json'
    if not path.exists():
        value = {k: protect(secrets.token_urlsafe(24)) for k in ('BUSINESS_DB_ROOT', 'BUSINESS_DB_PASSWORD', 'BUSINESS_APP_PASSWORD')}
        path.write_text(json.dumps(value), encoding='utf-8')
        who = subprocess.check_output(['whoami'], text=True).strip()
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', f'{who}:(F)'], check=True, capture_output=True)
    return {k: unprotect(v) for k,v in json.loads(path.read_text()).items()}


class Stack:
    def __init__(self):
        self.env = {**os.environ, **credentials()}
        self.owned = False
        self.lock = None

    def compose(self, *args, input=None, check=True):
        result = subprocess.run(['docker', 'compose', '-f', str(COMPOSE), *args],
            env=self.env, input=input, capture_output=True, timeout=300)
        if check and result.returncode:
            # Retain diagnostics after removing all local credentials.
            diagnostic=(result.stdout+result.stderr).decode('utf-8',errors='replace')
            for key in ('BUSINESS_DB_ROOT','BUSINESS_DB_PASSWORD','BUSINESS_APP_PASSWORD'):
                diagnostic=diagnostic.replace(self.env[key],'[redacted]')
            (LOCAL/'last-error.log').write_text(diagnostic,encoding='utf-8')
            raise RuntimeError(f'Compose {args[0]} failed; exit={result.returncode}')
        return result

    def running(self):
        return self.compose('ps', '--status', 'running', '-q').stdout.strip()

    def start(self):
        import msvcrt
        self.lock=(LOCAL/'lifecycle.lock').open('a+b')
        if os.fstat(self.lock.fileno()).st_size==0:
            self.lock.write(b'0');self.lock.flush()
        self.lock.seek(0)
        try:
            msvcrt.locking(self.lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:
            self.lock.close();self.lock=None
            raise RuntimeError('业务演示正在启动或已运行，请勿重复启动') from None
        if self.running():
            raise RuntimeError('已有业务演示服务正在运行，请回到其控制台或先正常结束；未接管已有服务。')
        self.owned = True
        self.compose('up', '-d')
        self.wait_http('http://127.0.0.1:18893/index.php', 600)
        self.wait_http('http://127.0.0.1:18894/', 90)
        r = self.compose('exec', '-T', 'erp', 'php', '/opt/nanomuse-seed.php')
        if b'SEEDED' not in r.stdout:
            raise RuntimeError('ERP initialization did not confirm success')
        self.seed_wiki()
        self.brand_assets()
        (LOCAL/'ready.json').write_text(json.dumps({'ready_at': time.time(), 'applications': ['Dolibarr 22.0.4','DokuWiki 2025-05-14a'], 'materials':len(PAGES)}))

    @staticmethod
    def wait_http(url, timeout):
        until = time.monotonic()+timeout
        with httpx.Client(trust_env=False, timeout=3, follow_redirects=True) as client:
            while time.monotonic()<until:
                try:
                    r=client.get(url)
                    if r.status_code==200:
                        return
                except httpx.HTTPError:
                    pass
                time.sleep(1)
        raise RuntimeError(f'Application not ready: {url}')

    def brand_assets(self):
        logo=(ROOT/'business/web/logo.png').read_bytes()
        for service,path in [('erp','/var/www/documents/mycompany/logos/guduu-os.png'),
                             ('erp','/var/www/documents/mycompany/logos/thumbs/guduu-os.png'),
                             ('wiki','/storage/data/media/wiki/logo.png')]:
            code="$p=$argv[1];if(!is_dir(dirname($p)))mkdir(dirname($p),0755,true);file_put_contents($p,stream_get_contents(STDIN));"
            self.compose('exec','-T',service,'php','-r',code,path,input=logo)
        config=self.compose('exec','-T','wiki','cat','/storage/conf/local.php').stdout.decode('utf-8')
        config='\n'.join(line for line in config.splitlines() if not line.strip().startswith("$conf['title']="))
        config+="\n$conf['title']='GuDuu OS · 团队知识库';\n"
        self.compose('exec','-T','wiki','php','-r',"file_put_contents('/storage/conf/local.php',stream_get_contents(STDIN));",input=config.encode('utf-8'))
        self.compose('exec','-T','wiki','chown','-R','33:33','/storage/data/media/wiki')

    def seed_wiki(self):
        self.compose('exec','-T','wiki','chown','-R','33:33','/storage')
        exists=self.compose('exec','-T','wiki','test','-f','/storage/nanomuse-seeded',check=False)
        if exists.returncode==0:
            return
        password=self.env['BUSINESS_APP_PASSWORD'].encode()
        hashed=self.compose('exec','-T','wiki','php','-r',
            'echo password_hash(stream_get_contents(STDIN), PASSWORD_BCRYPT);',input=password).stdout.decode().strip()
        conf="""<?php
$conf['title']='星河运营知识库';
$conf['lang']='zh';
$conf['useacl']=1;
$conf['superuser']='@admin';
$conf['disableactions']='register,resendpwd';
$conf['license']='0';
$conf['updatecheck']=0;
$conf['userewrite']=0;
"""
        files={'conf/local.php':conf,'conf/users.auth.php':f'#<?php exit()?>\npresenter:{hashed}:现场演示:presenter@example.invalid:user\n',
            'conf/acl.auth.php':'#<?php exit()?>\n* @ALL 0\n* @user 8\n', 'nanomuse-seeded':'1'}
        files.update({f'data/pages/{key.replace(":","/")}.txt':body for key,body in PAGES.items()})
        archive=io.BytesIO()
        with tarfile.open(fileobj=archive,mode='w') as tar:
            for name,body in files.items():
                content=body.encode('utf-8');info=tarfile.TarInfo(name)
                info.size=len(content);info.mode=0o644;info.uid=info.gid=33;info.mtime=int(time.time())
                tar.addfile(info,io.BytesIO(content))
        self.compose('exec','-T','wiki','tar','xf','-','-C','/storage',input=archive.getvalue())
        self.compose('exec','-T','wiki','chown','-R','33:33','/storage')
        self.compose('exec','-T','--user','33:33','wiki','php','/var/www/html/bin/indexer.php',check=False)

    def stop(self):
        try:
            if self.owned:
                self.compose('stop', check=False)
                self.owned=False
        finally:
            if self.lock:
                self.lock.close();self.lock=None

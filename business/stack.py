"""Own only this Compose project; encrypted credentials and non-destructive cleanup."""
import io
import json
import os
import re
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
        self.project=self.env.get('BUSINESS_PROJECT','nanomuse-business')
        self.volume_keys={'db':'BUSINESS_DB_VOLUME','documents':'BUSINESS_DOCUMENTS_VOLUME','wiki':'BUSINESS_WIKI_VOLUME'}
        self.pointer=LOCAL/'workspace.json'
        volumes={role:f'{self.project}_{role}' for role in self.volume_keys}
        if self.pointer.exists():
            volumes=json.loads(self.pointer.read_text(encoding='utf-8'))['volumes']
        self.set_volumes(volumes)

    def set_volumes(self,volumes):
        if set(volumes)!=set(self.volume_keys) or any(not re.fullmatch(re.escape(self.project)+r'_[a-z0-9_-]+',v) for v in volumes.values()):
            raise ValueError('工作区数据卷配置不合法')
        for role,key in self.volume_keys.items():self.env[key]=volumes[role]

    def volumes(self):
        return {role:self.env[key] for role,key in self.volume_keys.items()}

    @staticmethod
    def write_json(path,data):
        path.parent.mkdir(parents=True,exist_ok=True)
        temp=path.with_suffix('.pending')
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(path)

    def backups(self):
        result=[]
        for path in sorted((LOCAL/'backups').glob('*.json'),reverse=True):
            try:
                data=json.loads(path.read_text(encoding='utf-8'))
                if data.get('project')==self.project and data['volumes']!=self.volumes():
                    result.append({'id':path.stem,'created_at':data['created_at']})
            except (ValueError,KeyError):continue
        return sorted(result,key=lambda item:item['created_at'],reverse=True)[:20]

    def backup_volumes(self,backup_id):
        if not re.fullmatch(r'\d{8}T\d{6}Z-[a-f0-9]{8}',backup_id):raise ValueError('备份编号不合法')
        data=json.loads((LOCAL/'backups'/f'{backup_id}.json').read_text(encoding='utf-8'))
        if data['project']!=self.project:raise ValueError('备份不属于当前工作区')
        old=self.volumes()
        try:self.set_volumes(data['volumes'])
        finally:self.set_volumes(old)
        return data['volumes']

    def reset(self,backup_id=None):
        """Freeze old volumes as a recoverable backup; switch to fresh/restored volumes."""
        if not self.owned or not self.lock:raise RuntimeError('只能重置本进程启动的工作区')
        old=self.volumes()
        source=self.backup_volumes(backup_id) if backup_id else None
        target={r:f'{self.project}_{r}_r{secrets.token_hex(8)}' for r in self.volume_keys}
        if source==old:raise ValueError('此备份已是当前工作区')
        if backup_id:
            subprocess.run(['docker','volume','inspect',*source.values()],check=True,capture_output=True)
        snapshot=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'-'+secrets.token_hex(4)
        manifest=LOCAL/'backups'/f'{snapshot}.json'
        # Stop first so MariaDB and file stores are flushed; never remove old volumes.
        record={'project':self.project,'created_at':time.time(),'volumes':old,'status':'prepared'}
        try:
            self.compose('stop')
            self.write_json(manifest,record)
            if source:self._clone_volumes(source,target)
            self.set_volumes(target)
            self._start_services()
            self.write_json(self.pointer,{'volumes':target})
        except Exception:
            self.compose('stop',check=False)
            self.set_volumes(old)
            try:
                self._start_services()
                self.write_json(self.pointer,{'volumes':old})
                record['status']='rolled_back'
            except Exception:
                record['status']='recovery_failed'
                raise RuntimeError('重置失败；原始数据卷仍保留，请检查本地服务日志') from None
            finally:
                self.write_json(manifest,record)
            raise RuntimeError('重置失败，已恢复原工作区，数据未删除') from None
        record['status']='ready';self.write_json(manifest,record)
        return {'backup_id':snapshot,'restored_from':backup_id}

    def _clone_volumes(self,source,target):
        # Restore to copies: later editing must never mutate a retained snapshot.
        image='mariadb:11.4.5@sha256:49117dcc565cf51aa57ac5fca59ab31213402ff0eae6ffc13c46a37b938f7e4b'
        for role,name in target.items():
            exists=subprocess.run(['docker','volume','inspect',name],capture_output=True)
            if exists.returncode==0:raise RuntimeError('新的工作区数据卷已存在，未覆盖')
            subprocess.run(['docker','volume','create','--label',f'com.docker.compose.project={self.project}',
                '--label',f'com.docker.compose.volume={role}',name],check=True,capture_output=True)
            copy_name=f'{self.project}-copy-{secrets.token_hex(8)}'
            try:
                subprocess.run(['docker','run','--rm','--name',copy_name,'--network','none','--read-only','--user','0',
                    '--entrypoint','/bin/bash','--mount',f'type=volume,source={source[role]},target=/from,readonly',
                    '--mount',f'type=volume,source={name},target=/to',image,'-ec',
                    'set -o pipefail; tar -C /from -cf - . | tar -C /to -xf -'],check=True,capture_output=True,timeout=300)
            finally:
                subprocess.run(['docker','rm','-f',copy_name],capture_output=True)

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
        self._start_services()

    def _start_services(self):
        self.compose('up', '-d')
        self.wait_http(f'http://127.0.0.1:{self.env.get("BUSINESS_ERP_PORT","18893")}/index.php', 600)
        self.wait_http(f'http://127.0.0.1:{self.env.get("BUSINESS_WIKI_PORT","18894")}/', 90)
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

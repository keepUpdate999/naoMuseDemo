"""Portable distribution entry point; no global Python installation required."""
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    root=Path(__file__).resolve().parents[1]
    os.chdir(root)
    from desktop.connection import LocalAPI
    api=LocalAPI()
    logs=root/'.local/desktop';logs.mkdir(parents=True,exist_ok=True)
    # The local-only edition still requires Docker Desktop and private model setup.
    if not (root/'.local/model.json').exists():
        from configure_model import write_configuration
        import getpass
        print('GuDuu OS first-time local model setup (key stays on this PC).')
        base=input('OpenAI-compatible base URL: ').strip()
        model=input('Model name: ').strip()
        key=getpass.getpass('API Key (hidden): ')
        write_configuration(root,base,model,key)
    try:
        health=api.request('/health')
    except OSError:
        health=None
    if health and health.get('app')!='nanomuse-real-apps':
        raise RuntimeError('Port 18892 belongs to another service; it was preserved.')
    if not health:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:browser_installed=Path(pw.chromium.executable_path).is_file()
        if not browser_installed:
            subprocess.run([sys.executable,'-m','playwright','install','chromium'],check=True)
    with (logs/'assistant.out.log').open('ab') as out,(logs/'assistant.err.log').open('ab') as err:
        subprocess.Popen([str(Path(sys.executable).with_name('pythonw.exe')),'-m','desktop.main'],
                         cwd=root,stdout=out,stderr=err)
    if health:
        print('GuDuu OS is running. Use the floating assistant / system tray.');return
    # Child service owns its Compose lifecycle; exit via the assistant's workspace menu.
    (root/'.local/business').mkdir(parents=True,exist_ok=True)
    with (root/'.local/business/server.out.log').open('ab') as out:
        with (root/'.local/business/server.err.log').open('ab') as err:
            proc=subprocess.Popen([sys.executable,'real_server.py'],cwd=root,stdout=out,stderr=err,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
    (root/'.local/business/server.pid').write_text(str(proc.pid))
    print('Preparing local business applications. Watch the floating assistant for status.')
    for _ in range(900):
        if proc.poll() is not None:raise RuntimeError('Startup failed; see .local/business/server.err.log')
        try:
            if api.request('/health').get('ready'):return
        except OSError:pass
        time.sleep(1)
    raise RuntimeError('Applications are still starting; see local logs. The process was preserved.')


if __name__=='__main__':
    try:main()
    except Exception as exc:
        print(type(exc).__name__+': '+str(exc));input('Press Enter to close.');sys.exit(1)

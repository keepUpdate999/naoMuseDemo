"""Opt-in read-only desktop smoke against the already running local workspace.

No run/reset/shutdown endpoint and no model request. The real Qt controls connect
to the real service and use only 'open operation window'.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0,os.environ.get('GUDUU_QA_SOURCE_ROOT',str(Path(__file__).resolve().parents[1])))
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from desktop.connection import Connection, LocalAPI
from desktop.main import Assistant


def verify(output, port):
    output.mkdir(parents=True,exist_ok=True)
    api=LocalAPI(port);api.attach();before=api.request('/api/status')
    if before['running'] or before['resetting']:raise RuntimeError('Workspace is busy; no UI action was performed.')
    app=QApplication.instance() or QApplication([]);app.setQuitOnLastWindowClosed(False)
    connection=Connection(port)
    window=Assistant(connection,QSettings(str(output/'smoke.ini'),QSettings.IniFormat))
    errors=[];connection.failed.connect(lambda name,message:errors.append((name,message)))
    window.show();window.start()
    def wait(predicate):
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            app.processEvents()
            if predicate():return
            time.sleep(.03)
        raise AssertionError('Desktop smoke timeout: '+str(errors))
    try:
        wait(lambda:window.run.isEnabled())
        assert window.scenario.count()==6
        window.scenario.setCurrentIndex(1)
        first=window.prompt.toPlainText();QTest.mouseClick(window.swap,Qt.LeftButton)
        assert window.prompt.toPlainText()!=first
        QTest.mouseClick(window.open,Qt.LeftButton)
        wait(lambda:not window.pending)
        assert not errors
        window.toggle_fold();assert window.collapsed
        window.toggle_fold();assert window.record_area.isVisible()
        app.processEvents();window.grab().save(str(output/'floating-live-ready.png'))
        after=api.request('/api/status')
        assert before['calls']==after['calls'] and len(after['tabs'])==7
        assert after['browser_open'] and not after['running']
        report={'mode':'read-only actual Qt and service, no model calls','scenarios':window.scenario.count(),
                'tabs':len(after['tabs']),'model_calls_delta':after['calls']-before['calls'],
                'default_tasks':True,'window_restore':True,'collapse_expand':True,'errors':errors}
        import desktop
        report['desktop_source']=str(Path(desktop.__file__).resolve().parent)
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
    finally:
        connection.close();assert connection.wait(6000)
        window.quitting=True;window.tray.hide();window.close();app.processEvents()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=18892)
    parser.add_argument('--output',type=Path,default=Path('.local/desktop/evidence'))
    args=parser.parse_args();verify(args.output,args.port)

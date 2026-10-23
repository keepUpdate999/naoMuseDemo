"""Native floating controls. The service remains authoritative for all actions."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid

from PySide6.QtCore import Qt, QSettings, QLockFile
from PySide6.QtGui import QIcon, QGuiApplication
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QPlainTextEdit, QListWidget, QListWidgetItem,
    QSystemTrayIcon, QMenu, QMessageBox, QFileDialog)

from desktop.connection import Connection
from desktop.presets import variants

ROOT = Path(__file__).resolve().parents[1]
STATUS = {'idle':'等待任务', 'running':'正在执行', 'finished':'本轮已结束，请核对结果',
          'error':'执行遇到问题', 'stopped':'任务已停止', 'resetting':'正在恢复工作区',
          'interrupted':'服务重启，任务已中断'}
KINDS = {'user':'任务', 'assistant':'模型说明', 'action':'浏览器动作', 'result':'本轮结果',
         'error':'异常', 'stopped':'已停止', 'workspace':'工作区', 'browser':'浏览器'}


class Assistant(QWidget):
    def __init__(self, connection=None, settings=None):
        super().__init__()
        self.setWindowTitle('GuDuu OS · 悬浮任务助手')
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        self.setMinimumSize(340, 360)
        self.resize(390, 650)
        self.settings = settings or QSettings('GuDuu', 'FloatingAssistant')
        self.connection = connection or Connection()
        self.state = {}; self.scenarios = []; self.variant = 0
        self.connected = False; self.pending = False; self.quitting = False
        self.collapsed = False; self.last_events = None; self.visible_events = []
        self.old_resetting = False; self.last_request_id = None
        self.icon = QIcon(str(ROOT/'business/web/logo.png'))
        self.setWindowIcon(self.icon)
        layout = QVBoxLayout(self); layout.setSpacing(10); layout.setContentsMargins(16, 14, 16, 14)
        header = QHBoxLayout()
        logo = QLabel(); logo.setPixmap(self.icon.pixmap(36, 36)); header.addWidget(logo)
        title = QLabel('GuDuu OS'); title.setObjectName('brand'); header.addWidget(title)
        header.addStretch()
        self.fold = QPushButton('收起'); self.fold.clicked.connect(self.toggle_fold); header.addWidget(self.fold)
        layout.addLayout(header)
        self.status = QLabel('正在连接本地工作区…'); self.status.setWordWrap(True); layout.addWidget(self.status)
        self.notice = QLabel('选择预置任务即可执行，无需手动输入。'); self.notice.setWordWrap(True); self.notice.setObjectName('notice'); layout.addWidget(self.notice)
        self.status.setTextFormat(Qt.PlainText); self.notice.setTextFormat(Qt.PlainText)
        self.task_area = QWidget(); area = QVBoxLayout(self.task_area); area.setContentsMargins(0,0,0,0)
        area.addWidget(QLabel('选择任务'))
        self.scenario = QComboBox(); self.scenario.setObjectName('scenario'); self.scenario.currentIndexChanged.connect(self.choose); area.addWidget(self.scenario)
        self.prompt = QPlainTextEdit(); self.prompt.setObjectName('prompt'); self.prompt.setMaximumHeight(130); self.prompt.setPlaceholderText('服务就绪后自动填入预置任务'); self.prompt.textChanged.connect(self.controls); area.addWidget(self.prompt)
        buttons = QHBoxLayout(); self.swap = QPushButton('换个任务'); self.swap.clicked.connect(self.next_variant); buttons.addWidget(self.swap)
        self.run = QPushButton('智能执行操作'); self.run.setObjectName('primary'); self.run.clicked.connect(self.submit); buttons.addWidget(self.run, 1); area.addLayout(buttons)
        layout.addWidget(self.task_area)
        self.summary = QLabel(); self.summary.setWordWrap(True); self.summary.hide(); layout.addWidget(self.summary)
        self.summary.setTextFormat(Qt.PlainText)
        self.record_area = QWidget(); records = QVBoxLayout(self.record_area); records.setContentsMargins(0,0,0,0)
        record_header = QHBoxLayout(); record_header.addWidget(QLabel('工作记录 · 最新在上')); record_header.addStretch()
        self.latest = QPushButton('回到最新'); self.latest.clicked.connect(lambda:self.logs.scrollToTop()); record_header.addWidget(self.latest); records.addLayout(record_header)
        self.history = QComboBox(); self.history.addItem('当前工作区', ''); self.history.currentIndexChanged.connect(self.select_history); records.addWidget(self.history)
        self.logs = QListWidget(); self.logs.setWordWrap(True); self.logs.setSpacing(5); self.logs.setMinimumHeight(110); self.logs.setVerticalScrollMode(QListWidget.ScrollPerPixel); records.addWidget(self.logs,1)
        layout.addWidget(self.record_area, 1)
        footer = QHBoxLayout()
        self.stop = QPushButton('停止任务'); self.stop.clicked.connect(lambda:self.send('stop',{})); footer.addWidget(self.stop)
        self.open = QPushButton('操作窗口'); self.open.clicked.connect(self.open_browser); footer.addWidget(self.open)
        self.more = QPushButton('更多 ⋯'); self.menu = QMenu(self)
        self.menu.addAction('打开完整工作台', self.open_workbench)
        self.menu.addAction('导出当前工作记录', self.export)
        self.reset_action = self.menu.addAction('备份并重置工作区', self.reset)
        self.restore_menu = self.menu.addMenu('恢复历史备份')
        self.menu.addSeparator(); self.menu.addAction('退出助手（工作区继续运行）', self.quit_assistant)
        self.exit_action = self.menu.addAction('退出工作区', self.shutdown)
        self.more.setMenu(self.menu); footer.addWidget(self.more); layout.addLayout(footer)
        self.tray = QSystemTrayIcon(self.icon, self)
        tray_menu = QMenu(self); tray_menu.addAction('显示任务助手', self.reopen); tray_menu.addAction('退出助手（工作区继续运行）', self.quit_assistant)
        self.tray.setContextMenu(tray_menu); self.tray.setToolTip('GuDuu OS · 悬浮任务助手')
        self.tray.activated.connect(lambda reason:self.reopen() if reason in (QSystemTrayIcon.Trigger,QSystemTrayIcon.DoubleClick) else None)
        if QSystemTrayIcon.isSystemTrayAvailable():self.tray.show()
        self.setStyleSheet('''QWidget { background:#f6f5ef; color:#203c39; font-family:"Microsoft YaHei UI"; font-size:12px; }
            QLabel#brand {font-size:20px;font-weight:700;} QLabel#notice {color:#687873;}
            QPushButton {border:1px solid #d5ddd3; border-radius:7px; padding:8px; background:#fff;}
            QPushButton:hover {background:#e9eee5;} QPushButton:disabled {color:#9ba7a1;}
            QPushButton#primary {background:#24634f;color:white;font-weight:700;}
            QPushButton#primary:disabled {background:#9eafa6;}
            QPlainTextEdit,QListWidget,QComboBox {background:#fff;border:1px solid #d5ddd3;border-radius:7px;padding:6px;}
            QListWidget::item {padding:8px;border-bottom:1px solid #e9eee5;}
            QMenu {background:white;} QMenu::item {padding:8px 18px;} QMenu::item:selected {background:#e9eee5;}''')
        self.restore_position()
        self.connection.state_received.connect(self.update_state)
        self.connection.tasks_received.connect(self.update_tasks)
        self.connection.history_received.connect(self.show_history)
        self.connection.connection_changed.connect(self.connection_status)
        self.connection.completed.connect(self.command_done)
        self.connection.failed.connect(self.command_failed)
        self.controls()

    def start(self):self.connection.start()

    def restore_position(self):
        saved = self.settings.value('geometry')
        if saved:self.restoreGeometry(saved)
        screens = QGuiApplication.screens()
        rect = self.frameGeometry()
        if not saved or not any(s.availableGeometry().contains(rect.center()) for s in screens):
            available = QGuiApplication.primaryScreen().availableGeometry()
            self.resize(min(390,available.width()), min(650,available.height()-20))
            self.move(available.right()-self.width()-16, available.top()+20)
        available = max(screens, key=lambda s:s.availableGeometry().intersected(self.frameGeometry()).width()).availableGeometry()
        self.resize(min(self.width(),available.width()), min(self.height(),available.height()))
        self.move(max(available.left(), min(self.x(),available.right()-self.width()+1)),
                  max(available.top(), min(self.y(),available.bottom()-self.height()+1)))

    def selected(self):
        index = self.scenario.currentIndex()
        return self.scenarios[index] if 0 <= index < len(self.scenarios) else None

    def choose(self, index):
        self.variant = 0
        selected = self.selected()
        if selected:self.prompt.setPlainText(variants(selected)[0])
        self.controls()

    def next_variant(self):
        selected = self.selected()
        if selected:
            self.variant = (self.variant+1)%len(variants(selected))
            self.prompt.setPlainText(variants(selected)[self.variant])

    def controls(self):
        running = bool(self.state.get('running')); resetting = bool(self.state.get('resetting'))
        busy = self.pending or running or resetting
        for control in (self.scenario,self.swap,self.prompt):control.setEnabled(self.connected and not busy)
        self.run.setEnabled(self.connected and not busy and bool(self.selected()) and bool(self.prompt.toPlainText().strip()) and (self.state.get('remaining') is None or self.state.get('remaining',0)>0))
        self.stop.setEnabled(self.connected and running and not self.pending and not resetting)
        self.open.setEnabled(self.connected and not busy)
        self.reset_action.setEnabled(self.connected and not busy)
        self.restore_menu.setEnabled(self.connected and not busy)
        self.exit_action.setEnabled(self.connected and not self.pending and not resetting)

    def connection_status(self, connected, message):
        self.connected = connected
        self.status.setText(message)
        if not connected:self.pending = False
        self.controls()

    def update_state(self, state):
        if self.quitting:return
        self.state = state; self.connected = True
        self.status.setText(STATUS.get(state['status'], state['status']))
        if not self.scenarios or (self.old_resetting and not state.get('resetting')):
            self.scenarios = state['scenarios']; self.scenario.blockSignals(True)
            self.scenario.clear()
            for scenario in self.scenarios:self.scenario.addItem(scenario['name'])
            self.scenario.blockSignals(False); self.choose(0)
        self.old_resetting = state.get('resetting',False)
        running = state.get('running',False)
        self.task_area.setVisible(not running and not self.collapsed)
        self.summary.setVisible(running and not self.collapsed)
        if running:
            task_events = [e for e in state['events'] if e['kind']=='user' and e.get('task_id')==state.get('task_id')]
            self.summary.setText('当前任务：'+(task_events[-1]['text'][:150] if task_events else '正在执行，请查看工作记录'))
        if not self.history.currentData():self.render_events(state['events'])
        self.restore_menu.clear()
        for backup in state.get('backups',[]):
            label = time.strftime('%m-%d %H:%M',time.localtime(backup['created_at']))
            self.restore_menu.addAction(label, lambda checked=False,b=backup:self.reset(b['id']))
        self.controls()

    def render_events(self, events):
        filtered = [e for e in events if e['kind'] in KINDS]
        signature = [(e.get('id'),e.get('task_id'),e['kind'],e['time'],e['text']) for e in filtered]
        if signature == self.last_events:return
        self.last_events = signature; self.visible_events = filtered
        scroll = self.logs.verticalScrollBar(); position = scroll.value(); old_max = scroll.maximum()
        self.logs.clear()
        for event in reversed(filtered):
            text = event['text'].replace('nanoMuse','GuDuu OS')
            item = QListWidgetItem(f"{event['time']} · {KINDS[event['kind']]}\n{text[:360]}" )
            item.setToolTip(text); self.logs.addItem(item)
        if not filtered:self.logs.addItem('等待第一条任务。')
        self.logs.doItemsLayout()
        if position == 0:self.logs.scrollToTop()
        else:scroll.setValue(position+max(0,scroll.maximum()-old_max))

    def update_tasks(self, tasks):
        selected = self.history.currentData(); self.history.blockSignals(True); self.history.clear(); self.history.addItem('当前工作区', '')
        for task in tasks:
            label = time.strftime('%m-%d %H:%M',time.localtime(task['created']))
            self.history.addItem(f"{label} · {STATUS.get(task['status'],task['status'])} · {task['prompt'][:18]}", task['id'])
        index = self.history.findData(selected)
        self.history.setCurrentIndex(max(0,index)); self.history.blockSignals(False)

    def select_history(self):
        selected = self.history.currentData()
        if selected:self.connection.command('history',selected)
        else:self.render_events(self.state.get('events',[]))

    def show_history(self, task_id, events):
        if self.history.currentData()==task_id:self.render_events(events)

    def send(self, name, body):
        if self.pending or not self.connected:return
        self.pending = True; self.notice.setText('正在提交…'); self.controls()
        self.connection.command(name,body)

    def submit(self):
        if not self.run.isEnabled():return
        selected = self.selected(); self.last_request_id = uuid.uuid4().hex
        self.history.setCurrentIndex(0)
        self.send('run',{'scenario':selected['id'],'prompt':self.prompt.toPlainText().strip(),'request_id':self.last_request_id})

    def open_browser(self):
        if self.selected():self.send('open',{'scenario':self.selected()['id']})

    def command_done(self, name, result):
        self.pending = False
        if name=='run':self.state={**self.state,'running':True,'status':'running'}
        self.notice.setText({'run':'任务已提交，实际进度见下方工作记录。', 'stop':'已停止后续操作，已保存内容保留。',
            'open':'操作窗口已显示。','reset':'正在备份并恢复工作区，请等待完成。'}.get(name,'操作已完成。'))
        if name=='shutdown':self.quit_assistant()
        self.controls()

    def command_failed(self, name, message):
        if name=='history':return
        self.pending = False; self.notice.setText(message); self.controls()

    def confirm(self, title, message):
        return QMessageBox.question(self,title,message,QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes

    def reset(self, backup_id=None):
        if not self.confirm('恢复备份' if backup_id else '重置工作区', '先备份当前业务数据，再恢复所选历史数据。' if backup_id else '先备份当前业务数据，再恢复初始素材。模型配置、调用账本和工作记录保留。'):return
        self.send('reset',{'confirm':True,'backup_id':backup_id})

    def shutdown(self):
        message = '结束当前任务并关闭本工作区拥有的浏览器和业务服务。已保存内容保留。确认退出？'
        if self.confirm('退出工作区',message):self.send('shutdown',{})

    def open_workbench(self):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl(self.connection.api.base+'/'))

    def export(self):
        path, _ = QFileDialog.getSaveFileName(self,'导出工作记录','guduu-work-records.json','JSON (*.json)')
        if path:
            try:Path(path).write_text(json.dumps({'events':self.visible_events},ensure_ascii=False,indent=2),encoding='utf-8')
            except OSError:self.notice.setText('无法写入所选文件，请选择其他位置。')

    def toggle_fold(self):
        self.collapsed = not self.collapsed
        if self.collapsed:
            self.settings.setValue('geometry',self.saveGeometry())
            self.expanded_size = self.size(); self.setMinimumHeight(170)
            self.task_area.hide(); self.record_area.hide(); self.summary.hide(); self.fold.setText('展开'); self.resize(self.width(),190)
        else:
            self.setMinimumHeight(360); self.record_area.show(); self.fold.setText('收起')
            self.resize(self.expanded_size); self.update_state(self.state) if self.state else self.task_area.show()

    def reopen(self):self.showNormal(); self.raise_(); self.activateWindow()

    def closeEvent(self, event):
        if self.quitting:event.accept(); return
        if not self.collapsed:self.settings.setValue('geometry',self.saveGeometry())
        event.ignore()
        if self.tray.isVisible():self.hide()
        else:self.showMinimized()

    def quit_assistant(self):
        self.quitting = True
        if not self.collapsed:self.settings.setValue('geometry',self.saveGeometry())
        self.tray.hide(); self.connection.close(); self.hide()
        # Keep the Qt event loop alive until the network worker exits safely.
        self.connection.finished.connect(QApplication.instance().quit)
        if not self.connection.isRunning():QApplication.instance().quit()


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--port',type=int,default=18892)
    args = parser.parse_args()
    app = QApplication(sys.argv[:1]); app.setQuitOnLastWindowClosed(False)
    local = Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'GuDuuOS-FloatingAssistant'
    local.mkdir(parents=True,exist_ok=True)
    lock = QLockFile(str(local/f'assistant-{args.port}.lock'))
    if not lock.tryLock(100):
        QMessageBox.information(None,'GuDuu OS','悬浮助手已经运行，请从系统托盘打开。'); return 0
    window = Assistant(Connection(args.port)); window.show(); window.start()
    app.aboutToQuit.connect(window.connection.close)
    result = app.exec(); window.connection.close(); window.connection.wait(6000)
    lock.unlock(); return result


if __name__=='__main__':sys.exit(main())

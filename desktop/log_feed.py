"""Painted timeline cards with incremental reveal, no background focus changes."""
import re
from PySide6.QtCore import Qt, QSize, QRectF, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QStyledItemDelegate

KINDS = {'user':'任务', 'assistant':'模型说明', 'action':'浏览器动作', 'result':'本轮结果',
         'error':'异常', 'stopped':'已停止', 'workspace':'工作区', 'browser':'浏览器'}
TONES = {'result':'#347658','error':'#be4b58','stopped':'#927245','user':'#5268a2'}


class TimelineDelegate(QStyledItemDelegate):
    def __init__(self, feed):
        super().__init__(feed); self.feed=feed

    def dimensions(self, option, index):
        event=index.data(Qt.UserRole) or {}
        width=max(120,self.feed.viewport().width()-10)
        font=QFont(option.font);font.setPixelSize(12)
        bounds=QFontMetrics(font).boundingRect(0,0,width-34,4000,Qt.TextWordWrap,event.get('display',''))
        height=max(66,42+bounds.height())
        return event,width,height,font

    def sizeHint(self, option, index):
        event,width,height,_=self.dimensions(option,index)
        progress=self.feed.progress.get(event.get('key'),1)
        return QSize(width,max(2,round((height+7)*progress)))

    def paint(self, painter, option, index):
        event,width,height,font=self.dimensions(option,index)
        progress=self.feed.progress.get(event.get('key'),1)
        if progress<=0:return
        painter.save();painter.setRenderHint(QPainter.Antialiasing)
        painter.setClipRect(option.rect);painter.setOpacity(min(1,progress*1.7))
        painter.translate(0,-6*(1-progress))
        rect=QRectF(option.rect.x()+1,option.rect.y()+1,width-2,height)
        painter.setPen(QPen(QColor('#e7ebf2'),1))
        painter.setBrush(QColor('#edf3ff') if progress<.98 else QColor('#f9fafc'))
        painter.drawRoundedRect(rect,8,8)
        color=QColor(TONES.get(event.get('kind'),'#536d9c'))
        painter.setBrush(color);painter.setPen(Qt.NoPen);painter.drawEllipse(QRectF(rect.x()+12,rect.y()+14,5,5))
        meta=QFont(font);meta.setPixelSize(10);painter.setFont(meta);painter.setPen(QColor('#768195'))
        painter.drawText(QRectF(rect.x()+23,rect.y()+8,width-35,18),Qt.AlignLeft|Qt.AlignVCenter,
                         event.get('time','')+'  ·  '+KINDS.get(event.get('kind'),'工作区'))
        painter.setFont(font);painter.setPen(QColor('#344054'))
        painter.drawText(QRectF(rect.x()+12,rect.y()+34,width-26,height-38),Qt.TextWordWrap,event.get('display',''))
        painter.restore()


class LogFeed(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.keys=[];self.progress={};self.reduced_motion=False;self.new_count=0;self.initialized=False
        self.animation=QVariantAnimation(self);self.animation.setStartValue(0.0);self.animation.setEndValue(1.0)
        self.animation.setDuration(460);self.animation.setEasingCurve(QEasingCurve.OutCubic)
        self.animation.valueChanged.connect(self.animate_rows);self.animation.finished.connect(self.finish_animation)
        self.setItemDelegate(TimelineDelegate(self));self.setWordWrap(True)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel);self.setSelectionMode(QListWidget.NoSelection)

    @staticmethod
    def key(event):return repr((event.get('task_id'),event.get('id'),event['time'],event['kind'],event['text']))

    def set_events(self, events, animate=True):
        # Complete pending animation before calculating scroll anchors.
        self.animation.stop();self.progress.clear()
        bar=self.verticalScrollBar();position=bar.value();old_max=bar.maximum()
        ordered=list(reversed(events));keys=[self.key(event) for event in ordered]
        appended=self.initialized and (not self.keys or self.keys[0] in keys)
        old_keys=set(self.keys)
        new_keys=[key for key in keys if key not in old_keys] if appended else []
        self.keys=keys;self.new_count=len(new_keys);self.initialized=True
        self.clear()
        for event,key in zip(ordered,keys):
            text=re.sub('nanomuse','GuDuu OS',event['text'],flags=re.I)
            item=QListWidgetItem(f"{event['time']} · {KINDS[event['kind']]}\n{text[:360]}")
            item.setToolTip(text);item.setData(Qt.UserRole,dict(event,key=key,display=text[:360]));self.addItem(item)
        if not events:
            item=QListWidgetItem('等待第一条任务');item.setData(Qt.UserRole,{'display':'选择一个预置任务，工作进度会显示在这里。','kind':'workspace'});self.addItem(item)
        if new_keys and animate and not self.reduced_motion and position<=2 and self.isVisible():
            self.progress={key:0 for key in new_keys[:8]};self.animation.start()
        self.doItemsLayout()
        if position<=2:self.scrollToTop()
        else:bar.setValue(position+max(0,bar.maximum()-old_max))

    def animate_rows(self, value):
        self.progress={key:float(value) for key in self.progress}
        self.doItemsLayout();self.viewport().update()

    def finish_animation(self):
        self.progress.clear();self.doItemsLayout();self.viewport().update()

    def resizeEvent(self,event):
        super().resizeEvent(event);self.doItemsLayout()

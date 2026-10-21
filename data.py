"""Fictional, repeatable fixtures; no personal or production data."""
import json
import sqlite3
from pathlib import Path


def seed():
    names = ['场地布置', '物资采购', '嘉宾确认', '海报设计', '设备调试', '签到准备', '交通指引', '志愿者培训', '茶歇安排', '节目彩排', '摄影准备', '会后回访']
    return {
        'tasks': [{'id': i + 1, 'title': n, 'owner': ['林悦', '陈舟', '周宁'][i % 3], 'status': '待处理', 'date': '2026-11-08'} for i, n in enumerate(names)],
        'orders': [{'id': f'DEMO-{i:03}', 'title': ['展架', '茶歇物资', '活动手册'][i % 3], 'amount': i * 110, 'status': ['待处理', '已完成', '运输中'][i % 3], 'detail': f'虚构物资订单 {i}，仅用于现场演示。'} for i in range(1, 31)],
        'notes': [], 'form': {'name': '', 'session': '上午场', 'people': 1, 'remark': ''},
    }


ARTICLES = [{'id': i + 1, 'title': title, 'body': body} for i, (title, body) in enumerate([
    ('开放日活动详情', '星河开放日于2026年11月8日09:00至12:00举行。地点：星河体验中心二楼。请携带水杯、笔记本和报名确认信息。'),
    ('开放日停车说明', '停车入口位于星河体验中心东门。进入后沿蓝色指示牌前往B区，步行到二楼签到。'),
    ('公共交通说明', '乘坐演示线路18路，在体验中心站下车，步行至南门。'),
    ('入场规则', '活动开始前15分钟签到，请出示报名确认信息。'),
    *[(f'{name}指南', f'{name}由现场工作人员协助办理。请前往一楼服务台咨询，所有资料均为虚构演示内容。') for name in ['志愿者', '茶歇', '摄影', '舞台', '物资', '签到', '讲座', '工作坊', '失物招领', '无障碍通行', '休息区', '展台', '讲师', '急救', '雨天安排', '离场']]
])]


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with sqlite3.connect(path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS state (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
            for key, value in seed().items():
                db.execute('INSERT OR IGNORE INTO state VALUES (?, ?)', (key, json.dumps(value, ensure_ascii=False)))

    def read(self):
        with sqlite3.connect(self.path) as db:
            return {k: json.loads(v) for k, v in db.execute('SELECT name, value FROM state')}

    def write(self, key, value):
        if key not in seed():
            raise ValueError('Unknown dataset')
        with sqlite3.connect(self.path) as db:
            db.execute('UPDATE state SET value=? WHERE name=?', (json.dumps(value, ensure_ascii=False), key))

    def reset(self, scene):
        key = {'table': 'tasks', 'transfer': 'notes', 'notes': 'notes', 'orders': 'orders', 'form': 'form'}.get(scene)
        if key:
            self.write(key, seed()[key])

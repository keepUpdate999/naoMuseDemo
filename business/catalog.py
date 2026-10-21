ERP='http://127.0.0.1:18893'
WIKI='http://127.0.0.1:18894'
SCENARIOS=[
    dict(id='customer',name='客户跟进',app='Dolibarr · 客户管理',url=ERP+'/societe/list.php',
         prompt='在客户系统找到“星河文化传媒”，把公开备注中的下次跟进改为“11月5日前确认设备清单和纸质资料数量”，保留其他信息并保存。',
         checks='客户公开备注更新，其他客户未变化。'),
    dict(id='orders',name='订单查找',app='Dolibarr · 订单管理',url=ERP+'/commande/list.php',
         prompt='在客户订单中查找“星河文化传媒”的订单，打开金额最高的一张，告诉我客户订单号、金额和服务内容。',
         checks='查找客户订单，查看金额与服务明细。'),
    dict(id='transfer',name='跨系统整理简报',app='Dolibarr → DokuWiki → Dolibarr',url=ERP+'/societe/list.php',
         prompt=f'读取星河文化传媒的客户信息和一张订单明细，在知识库 {WIKI}/doku.php?id=work:followup 编辑“客户跟进简报”，写入客户名称、客户订单号（订单明细里的“顾客编号”，NM-ORD开头）、系统订单号、金额和下一步事项并保存；两个订单编号须分别标明。最后回星河文化传媒的客户卡片，在客户公开备注末尾追加“跟进简报已整理”，已有时不重复追加。订单只查阅，不修改订单或订单备注。',
         checks='两套应用间切换，知识库内容与订单吻合，客户备注出现回写记录。'),
    dict(id='document',name='执行清单与追加修改',app='DokuWiki · 项目文档',url=WIKI+'/doku.php?id=projects:open_day',
         prompt=f'阅读开放日活动方案，在 {WIKI}/doku.php?id=work:checklist 编辑会前执行清单，整理设备、资料、签到三项及各自时间，保存。然后追加“检查现场网络并准备离线资料”，再次保存。',
         checks='整理项目执行事项，支持保存和追加更新。'),
    dict(id='search',name='检索运营资料',app='DokuWiki · 全文检索',url=WIKI+'/doku.php?id=start',
         prompt='在知识库搜索开放日停车说明，打开正文，告诉我停车入口在哪一侧、停在哪个区；再查签到说明，告诉我提前多久到场以及携带哪些物品。',
         checks='检索运营资料，汇总相关信息与来源。'),
    dict(id='contact',name='联系人录入与修改',app='Dolibarr · 联系人',url=ERP+'/contact/list.php',
         prompt='新建活动联系人：姓“陈”，所属公司“星河文化传媒”，名“晨”，职位“上午场联络人”，邮箱 visitor@example.invalid。保存后重新编辑，把职位改成“下午场联络人”，保留其他字段，再保存。',
         checks='创建和更新联系人，保留公司与联系方式。'),
]

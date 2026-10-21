<?php
// Initialization only. Never exposed to the agent or served by Apache.
define('NOLOGIN', 1);
define('NOCSRFCHECK', 1);
require '/var/www/html/master.inc.php';
require_once DOL_DOCUMENT_ROOT.'/core/lib/admin.lib.php';
dolibarr_set_const($db, 'MAIN_MONNAIE', 'CNY', 'chaine', 0, '', 1);
dolibarr_set_const($db, 'MAIN_APPLICATION_TITLE', 'GuDuu OS', 'chaine', 0, '', 1);
dolibarr_set_const($db, 'MAIN_INFO_SOCIETE_LOGO', 'guduu-os.png', 'chaine', 0, '', 1);
dolibarr_set_const($db, 'MAIN_INFO_SOCIETE_LOGO_SQUARRED_MINI', 'guduu-os.png', 'chaine', 0, '', 1);
dolibarr_set_const($db, 'MAIN_SHOW_LOGO', '1', 'chaine', 0, '', 1);
dolibarr_set_const($db, 'MAIN_HTML_TITLE', 'showapp', 'chaine', 0, '', 1);
dolibarr_set_const($db, 'MAIN_FAVICON_URL', '/viewimage.php?modulepart=mycompany&file=logos%2Fguduu-os.png', 'chaine', 0, '', 1);
$db->query("UPDATE ".MAIN_DB_PREFIX."societe SET note_public=REPLACE(note_public,'nanoMuse','GuDuu OS') WHERE note_public LIKE '%nanoMuse%'");
$conf->currency='CNY';
require_once DOL_DOCUMENT_ROOT.'/societe/class/societe.class.php';
require_once DOL_DOCUMENT_ROOT.'/contact/class/contact.class.php';
require_once DOL_DOCUMENT_ROOT.'/commande/class/commande.class.php';
$user = new User($db);
$user->fetch('', 'presenter');
$user->getrights();
if (getDolGlobalInt('NANOMUSE_BUSINESS_SEEDED')) { echo "ALREADY_SEEDED\n"; exit(0); }
if ($db->query("SELECT rowid FROM ".MAIN_DB_PREFIX."societe WHERE nom='星河文化传媒'")) {
    $r=$db->query("SELECT rowid FROM ".MAIN_DB_PREFIX."societe WHERE nom='星河文化传媒'");
    if ($db->num_rows($r)>0) { dolibarr_set_const($db,'NANOMUSE_BUSINESS_SEEDED','1','chaine',0,'',1); echo "ALREADY_SEEDED\n"; exit(0); }
}
$names=['星河文化传媒','远山教育科技','青禾设计事务所','蓝海会展服务','云帆创新中心','松林文化中心','晨光体育发展','北辰企业服务','知行书院','澄明建筑设计','海棠公益中心','望岳科技园','南风艺术空间','星桥社区服务','明德培训中心','启航创客空间','新芽环保科技','禾木品牌策划','听雨音乐工作室','拾光摄影机构','知微数据服务','悦动青年中心','天际机器人实验室','溪谷自然教育'];
$ids=[];
$db->begin();
foreach($names as $i=>$name) {
    $s=new Societe($db);
    $s->name=$name; $s->client=1; $s->code_client=-1;
    $s->email=sprintf('client%02d@example.invalid',$i+1);
    $s->town=['杭州','上海','苏州','南京'][$i%4];
    $s->address='体验路'.($i+101).'号（演示地址）';
    $s->note_public=$i===0 ? '开放日合作客户。联系人：林悦；需求：开放日会场、签到及纸质资料。下次跟进：确认设备清单。' : '活动运营演示客户；资料由GuDuu OS项目生成。';
    $id=$s->create($user);
    if($id<=0) { $db->rollback(); fwrite(STDERR,'Customer seed failed: '.json_encode(['result'=>$id,'error'=>$s->error,'errors'=>$s->errors,'db'=>$db->lasterror(),'user'=>$user->id],JSON_UNESCAPED_UNICODE)); exit(1); }
    $ids[]=$id;
}
$p=new Contact($db);$p->socid=$ids[0];$p->lastname='林悦';$p->firstname='';$p->poste='活动负责人';$p->email='lin.yue@example.invalid';
if($p->create($user)<=0) { $db->rollback();fwrite(STDERR,'Contact seed failed');exit(1); }
for($i=1;$i<=18;$i++) {
    $o=new Commande($db);$o->socid=$ids[($i-1)%6];$o->date=time();$o->date_commande=time();
    $o->ref_client=sprintf('NM-ORD-%03d',$i);$o->note_public='开放日活动服务订单（虚构业务素材）';
    $id=$o->create($user);
    if($id<=0) { $db->rollback();fwrite(STDERR,'Order seed failed: '.$o->error);exit(1); }
    $qty=($i%4)+1; $price=($i*180)+600;
    $res=$o->addline('开放日会务服务：场地、签到与活动资料', $price, $qty, 0);
    if($res<=0) { $db->rollback();fwrite(STDERR,'Order line failed: '.$o->error);exit(1); }
}
$db->commit();
dolibarr_set_const($db,'NANOMUSE_BUSINESS_SEEDED','1','chaine',0,'',1);
echo "SEEDED 24 customers, 1 contact, 18 draft orders\n";

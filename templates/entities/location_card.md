---
id: {{slot:location_id|loc_001}}
name: "{{slot:location_name|地名/场景/秘境名}}"
type: place
danger_tier: {{slot:location_danger_tier|3}}
danger_level: "{{slot:location_danger_desc|安全腹地/争端前线/绝地死境}}"
faction: "{{slot:location_faction|所属势力/无主之地/中立区域}}"
sensory_anchor: "{{slot:location_sensory_anchor|空间格局、气味、光线与核心中心物象}}"
environment_rules:
  - "{{slot:location_rule_1|特殊环境法则/负面状态1}}"
  - "{{slot:location_rule_2|准入门槛/钥匙信物2}}"
status: active
schema_version: novel-studio.location/v2
---

<!-- 💡【Stage 0 架构师指南（填写后可删）】
     关键场景卡用于锁定故事核心爆发点的空间格局与感官细节。
     防止场景描写漂移（例如上一章是千丈宽阔地宫，下一章写得像逼仄小水沟；或交通用时前后吃书）。
     复制至 entities/locations/<地名>.md 并填实。
     ★ 语感规范：通俗直白大白话、空间格局与感官物象清晰易懂、严禁堆砌生涩晦涩词汇！
     ★ 状态同步提醒：本 YAML 中的 id, name, type, danger_tier, environment_rules, sensory_anchor, faction, status 属于 实体四表（persons/items/factions/places） 法定白名单；danger_level 属于卡片语义扩展，入库四表时请保留白名单字段。
     ★ 全题材适配：
       - 玄幻/仙侠：断魂溶洞/诸神战墟/圣宫主峰，填天地威压、禁空阵法、地热寒煞；
       - 都市/商战：滨海半岛顶奢庄园/旧港货柜集散地/云端秘密拍卖厅，填监控盲区、安防等级、交通动线；
       - 科幻/星际：废弃空间跃迁锚点/红矮星辐射采矿井/赛博深层地下黑市，填人工重力倍数、辐射指数、生命维持能耗；
       - 历史/权谋：临渊古道关隘/紫禁内廷御书房/边军烽火孤台，填地势险要、飞鸟难度、换马驿站里程。 -->

# {{slot:location_name|地名/场景/秘境名}}

## 基础空间与地理定位

- **地名全称与常见别称**：{{slot:location_name}}（别名：{{slot:location_aliases|如：断魂洞、荒古禁地 / 7号废弃空港}}）
- **地势险要度与危险评级（Danger Tier & Level）**：
  {{slot:location_danger_desc}}（Danger Tier: {{slot:location_danger_tier|3}} ｜ 1 安全腹地 ~ 10 必死绝境）
- **所属大区域与地缘坐标**：
  {{slot:location_region|沧澜神域南域荒古禁林深处 / 维多利亚港西岸地下管网 / 柯伊伯带第三前哨站}}
- **掌控势力与管辖权**：{{slot:location_faction}}

---

## 标志性空间格局与感官物象（Sensory Anchor）

- **空间尺度与建筑/自然格局**：
  {{slot:location_layout|例如：高百丈的天然钟乳溶洞，阴冷潮湿，地面布满暗金色碎石 / 白玉铺就的九层飞檐宏伟大殿}}
- **感官物象（光线、气味、温度、音效）**：
  {{slot:location_sensory|刺骨冰冷的阴煞寒风、空气中弥漫的淡淡焦灼煞气与干涸血腥味、洞口巨石崩塌的轰鸣}}
- **核心中心物象（Centerpiece Anchor）**：
  {{slot:location_sensory_anchor|溶洞正中央静静横陈的万年青铜神棺 / 悬挂大殿之上的黑金牌匾}}

---

## 环境法则、特殊机制与准入门槛（Environment Rules）

- **特殊环境法则与负面减益（Environmental Debuffs）**：
  - 法则 1：{{slot:location_rule_1|例如：全场压制神识感知与灵力流转五成 / 无重力强辐射环境}}
  - 法则 2：{{slot:location_rule_2|例如：地面布满易燃地煞毒瘴，动用明火极易引发连环轰爆}}
- **准入门槛与钥匙/权限**：
  {{slot:location_key|非通玄境不可御寒抗毒 / 需持有特级权限门禁芯片}}
- **交通动线与距离标尺（防瞬移瞬到）**：
  {{slot:location_travel_time|自宗门山门乘战舟需半日 / 常人徒步穿行需三天，沿途有两处盘查岗哨}}

---

## 历史大事件与场景变迁（Event Footprints）

- [第一现场] 第 {{slot:loc_event_ch|1}} 章：{{slot:loc_event_desc|萧灵汐在此强行双修唤醒神棺，主角万年神躯复苏，第一案发核心现场}}；

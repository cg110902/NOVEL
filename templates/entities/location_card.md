---
id: {{slot:location_id|loc_001}}
name: "{{slot:location_name|地名/场景/场所名}}"
type: place
danger_tier: {{slot:location_danger_tier|1}}
danger_level: "{{slot:location_danger_desc|日常生活场所/核心办公地/公共活动区/特殊场景}}"
faction: "{{slot:location_faction|所属机构/管辖归属/中立区域}}"
sensory_anchor: "{{slot:location_sensory_anchor|空间格局、采光、氛围与核心视觉物象}}"
environment_rules:
  - "{{slot:location_rule_1|场所规则/出入准则1}}"
  - "{{slot:location_rule_2|环境特点/特殊氛围2}}"
status: active
schema_version: novel-studio.location/v2
---

<!-- 💡【Stage 0 架构师通用指南（填写后可删除本注释）】
     本模板用于锁定故事核心场景的空间格局与感官细节，防止描写漂移：
     - 言情/都市：温馨咖啡馆、高端写字楼、大学校园、老洋房画室、海滨观景台；
     - 悬疑/刑侦：案发现场、老旧档案库、地下停车场、审讯室、滨海废弃仓库；
     - 玄幻/科幻/历史：宗门大殿、灵脉秘境、星舰驾驶舱、皇家别苑。
     ★ 规范：空间格局清晰可感，未定细节均可写“自行设定”。 -->

# {{slot:location_name|地名/场景/场所名}}

---

## 一、 基础空间与地理定位

- **场所全称与别名**：{{slot:location_name}}（别名：{{slot:location_aliases|如：中心大厦顶层 / 转角咖啡屋 / 栖霞别院（自行设定）}}）
- **场所属性与安全/氛围评级（Danger Tier & Level）**：
  {{slot:location_danger_desc}}（Danger Tier: {{slot:location_danger_tier|1}} ｜ 1 常规生活/安全 ~ 10 极端考验/核心冲突地）
- **所属大区域与地理位置**：
  {{slot:location_region|城市中心商业区 / 老城区深处 / 宗门主峰东麓（自行设定）}}
- **归属方与管辖权**：{{slot:location_faction}}

---

## 二、 空间格局与感官细节（Sensory Anchor）

- **空间尺度与建筑/环境格局**：
  {{slot:location_layout|例如：挑高宽敞的落地窗大厅，阳光通透，木质长桌与绿植点缀 / 幽静素雅的庭院（自行设定）}}
- **感官物象（光线、气味、温度、声效）**：
  {{slot:location_sensory|淡淡的现磨咖啡香气、柔和轻缓的背景音乐、清爽宜人的空气温度（自行设定）}}
- **核心标志性物象（Centerpiece Anchor）**：
  {{slot:location_sensory_anchor|靠窗边的一方静谧座位 / 大厅正中央的标志性设计（自行设定）}}

---

## 三、 环境规则与通行要求（Environment Rules）

- **场所规则与特点**：
  - 规则 1：{{slot:location_rule_1|需凭门禁卡或预约进入 / 安静私密的交谈空间（自行设定）}}
  - 规则 2：{{slot:location_rule_2|出入登记制度 / 特殊氛围约定（自行设定）}}
- **准入门槛与要求**：
  {{slot:location_key|工作日正常开放 / 需专属工作证或提前邀约（自行设定）}}
- **交通动线与距离标尺**：
  {{slot:location_travel_time|距主角住所车程约二十分钟 / 地铁直达（自行设定）}}

---

## 四、 关键事件与场景印记（Event Footprints）

- [重要节点] 第 {{slot:loc_event_ch|1}} 章：{{slot:loc_event_desc|故事开篇核心互动在此展开，主角初次登场或重要契机发生（自行设定）}}；

---
id: {{slot:faction_id|fac_001}}
name: "{{slot:faction_name|势力/宗门/组织全称}}"
type: faction
scale_tier: {{slot:faction_scale_tier|4}}
tier_name: "{{slot:faction_tier_name|顶尖大宗/区域霸主/跨国财阀/隐世门阀}}"
attitude: {{slot:faction_attitude|neutral}}
leader: "{{slot:faction_leader|掌权领袖角色名}}"
headquarters: "{{slot:faction_hq|总部据点/山门祖庭地名}}"
core_assets:
  - "{{slot:faction_core_asset_1|王牌资产/护宗底蕴1}}"
  - "{{slot:faction_core_asset_2|垄断产业/命脉资源2}}"
diplomacy:
  "{{slot:faction_rival_1|死敌势力名}}": "hostile"
  "{{slot:faction_ally_1|盟友势力名}}": "allied"
status: active
schema_version: novel-studio.faction/v2
---

<!-- 💡【Stage 0 架构师指南（填写后可删）】
     长篇小说的冲突核心往往是宗门、门阀、跨国财阀或行星阵营之间的集团战争。
     本卡用于锁定核心势力的掌权架构、垄断资源、护宗王牌与敌友外交网络。
     复制至 entities/factions/<势力名>.md 并填实。
     ★ 语感规范：通俗直白大白话、利益算计与爽点博弈分明、拒绝空洞堆砌！
     ★ 状态对齐：本 YAML 中的 id, name, type, scale_tier, tier_name, attitude, leader, headquarters, core_assets, diplomacy, status 均已与 实体四表（persons/items/factions/places） 法定 Schema 100% 闭环对齐！
     ★ 全题材适配：
       - 玄幻/仙侠：水云圣宫/焚天神谷/太古世家，填功法道统、护山大阵、灵矿命脉、敌对死仇；
       - 都市/商战：盛天控股集团/暗夜黑市/跨境财阀，填股权结构、控股产业、安保武装、商战死对头；
       - 科幻/星际：远征联合舰队/轨道殖民评议会/赛博巨型企业，填战舰编制、跃迁门垄断、星区主权；
       - 历史/权谋：东宫太子党/陇西门阀/江南织造局，填朝堂根基、兵马钱粮、朋党依附。 -->

# {{slot:faction_name|势力/宗门/组织全称}}

## 基础档案与势力定位

- **势力全称与常见简称**：{{slot:faction_name}}（简称：{{slot:faction_short|如：圣宫、水云宫、盛天资本}}）
- **势力规模与定位（Scale Tier & Name）**：{{slot:faction_tier_name}}（Scale Tier: {{slot:faction_scale_tier|4}} ｜ 辐射范围：{{slot:faction_coverage|统辖三州七十二城 / 跨越五个星区 / 掌控某行业半数供应链}}）
- **核心特色与运作方式**：{{slot:faction_specialty|专修极道水系道统 / 高频量化黑天鹅 / 生物义体垄断研发 / 军机要务统揽}}
- **总部据点与地缘环境**：{{slot:faction_hq}}（{{slot:faction_env|云雾缭绕的三万丈玄水主峰 / 陆家嘴超甲级云端写字楼 / 近地轨道防御要塞}}）

---

## 权力架构与核心人物名册（Hierarchy & Key Figures）

- **最高掌权领袖**：{{slot:faction_leader}}（当前实力/定位：{{slot:faction_leader_realm|闭关半步神海老祖 / 董事局主席 / 舰队总司令}}）
- **第二序列 / 继承人/副手**：{{slot:faction_second_in_command|例如：圣女萧灵汐 / 执行董事 / 第一副官}}
- **核心骨干与执行层**：{{slot:faction_elders|执法长老、首席战略顾问、舰队参谋长}}
- **内部派系倾轧与暗流**：{{slot:faction_internal_strife|正统护道派 vs 勾结外敌篡权党 / 保守创业元老 vs 激进资本系}}

---

## 核心垄断资产、底蕴与防御武装（Core Assets & Defense）

- **王牌防御 / 终极安全系统**：{{slot:faction_defenses|九天玄水大阵 / 重组杀阵 / 专属安保部队防弹阵列 / 行星轨道防御网}}
- **核心命脉产业与垄断资源（Core Assets）**：
  - 核心资产 1：{{slot:faction_core_asset_1}}
  - 核心资产 2：{{slot:faction_core_asset_2}}
- **常规武装与精锐编制**：{{slot:faction_military|三千水云白甲卫 / 精锐外勤特别行动组 / 两个突击巡洋舰中队}}

---

## 外交拓扑与敌友阵营网络（Diplomacy Network）

- **生死死敌（Mortal Enemy · 绝对敌对）**：
  - 势力名：{{slot:faction_rival_1}}（矛盾起因：{{slot:faction_rival_cause|争夺本源道统 / 恶意吞并血仇}}）
- **战略盟友（Allied · 唇齿相依）**：
  - 势力名：{{slot:faction_ally_1}}（同盟基石：{{slot:faction_ally_basis|联姻守望 / 互锁供应链}}）
- **中立贸易伙伴（Neutral · 利益往来）**：
  - {{slot:faction_neutral|商盟盘口 / 中立星际自由港 / 影子钱庄}}

---

## 存亡变迁与不可逆大事件轨迹（Milestones）

- [历史大事件] 第 {{slot:fac_event_ch|5}} 章：{{slot:fac_event_desc|大长老逼宫败露被一举肃清，主角晋升为最高战略尊荣，势力底蕴彻底稳固}}；

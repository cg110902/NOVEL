---
id: {{slot:item_id|it_001}}
name: "{{slot:item_name|道具/装备/法宝名}}"
type: item
tier_rank: {{slot:item_tier_rank|3}}
tier_name: "{{slot:item_tier_name|品阶/代际/估值}}"
holder: "{{slot:item_holder|当前持有者角色名}}"
location: "{{slot:item_location|随身携带/储物戒/某宝库}}"
charges: {{slot:item_charges|-1}}
max_charges: {{slot:item_max_charges|-1}}
cost_per_use: "{{slot:item_cost_per_use|单次催动代价/消耗}}"
durability: "{{slot:item_durability|完好/微损/耐久度}}"
sensory_anchor: "{{slot:item_sensory_anchor|材质、光泽、触感与重量}}"
status: active
schema_version: novel-studio.item/v2
---

<!-- 💡【Stage 0 架构师指南（填写后可删）】
     长篇中重要道具（神舟、兵刃、本命信物、核心机密账册、高维奇物）是剧情爆发的核心物象！
     没有独立道具卡，模型经常会吃书：忘记道具在谁手里、长什么样、剩多少次使用机会。
     将本模板复制至 entities/items/<道具名>.md 并填实。
     ★ 全题材适配：
       - 玄幻/仙侠：九劫神棺/破虚飞舟/本命剑胚，填品阶灵石消耗、神识绑定；
       - 都市/商战：离岸信托加密私钥/定制防弹豪车/特质机械表，填估值、使用权限与物理抗性；
       - 科幻/星际：反物质微型引擎/四代单兵纳米装甲/量子信标，填科技代际、能量匣充能、过载风险；
       - 历史/权谋：先皇遗诏/调兵虎符/前朝玉玺，填真伪防伪印鉴、见符如见人的政治律则。 -->

# {{slot:item_name|道具/装备/法宝名}}

## 基础档案与品阶定位

- **道具全称与常见别名**：{{slot:item_name}}（别名：{{slot:item_aliases|如：太古神舟、龙首战舟 / 暗夜黑匣}}）
- **品阶评定与稀缺度（Tier Rank & Name）**：{{slot:item_tier_name}}（Tier Rank: {{slot:item_tier_rank|3}} ｜ {{slot:item_scarcity|世所罕见 / 镇派禁器 / 独一无二}}）
- **当前合法持有者**：**{{slot:item_holder}}**（严禁在无夺宝或转赠剧情下私自易手）
- **存放位置与流转状态**：{{slot:item_location|随身佩戴 / 存入丹田 / 随身公文箱 / 某地下金库}}

---

## 外观材质与物理感知物象（Sensory Anchor）

- **材质、色泽与微观质感**：
  {{slot:item_material|例如：通体玄黑覆盖黑龙细鳞、触手冰凉刺骨 / 航空级钛合金哑光拉丝涂层}}
- **尺寸、受力重量与辨识声响**：
  {{slot:item_size_weight|长百丈宽三十丈的巨型龙首战舟，破空伴随沉闷雷鸣 / 掌心大小却沉如玄铁，握住时有细微脉冲嗡鸣}}
- **感官物象总结（Sensory Anchor）**：
  {{slot:item_sensory_anchor|黑鳞覆体、暗金纹路流转、冷冽如千年寒铁}}

---

## 核心功效、催动门槛与损耗代价（Depletion & Cost）

- **核心主动威能（物理/社会效果）**：
  {{slot:item_main_power|撕裂虚空横渡八千里 / 释放万道玄水剑气轰杀辟海境 / 调动五千万弹药}}
- **催动条件与能耗门槛（Cost Per Use）**：
  {{slot:item_cost_per_use|每次催动消耗纯净灵石十万枚 / 需指纹与声纹双重生物识别 / 消耗自身三成精血}}
- **充能与损耗规则（Charges & Durability）**：
  - 剩余可用充能：{{slot:item_charges|-1}} / 最大上限：{{slot:item_max_charges|-1}}（-1 表示非计数充能型）
  - 耐久与磨损状态：{{slot:item_durability|完好无损 / 剑锋有三道细微豁口，需特定灵液修复}}

---

## 流转变迁与升级重铸轨迹（Lifecycle Ledger）

- [初始获得] 第 {{slot:item_obtain_ch|1}} 章：{{slot:item_obtain_event|在荒古断魂洞中现世 / 家族遗嘱继承 / 拍卖会击败竞争对手夺得}}；
- [重大演变] 第 {{slot:item_evolve_ch|8}} 章：{{slot:item_evolve_event|由主角引动真火修复帝纹 / 升级最新一代神经元接驳核心}}；

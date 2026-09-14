---
id: {{slot:item_id|it_001}}
name: "{{slot:item_name|道具/装备/信物/物品名}}"
type: item
tier_rank: {{slot:item_tier_rank|3}}
tier_name: "{{slot:item_tier_name|品阶/规格/估值}}"
holder: "{{slot:item_holder|当前持有者角色名}}"
location: "{{slot:item_location|随身携带/专属办公室/某处所}}"
charges: {{slot:item_charges|10}} # 若为非计数型道具，填实后可保留或设为常规数值
max_charges: {{slot:item_max_charges|10}} # 若为非计数型道具，填实后可保留或设为常规数值
cost_per_use: "{{slot:item_cost_per_use|单次使用代价/维护消耗}}"
durability: "{{slot:item_durability|完好/微损/成色良好}}"
sensory_anchor: "{{slot:item_sensory_anchor|材质、质感、触感与特征}}"
status: active
schema_version: novel-studio.item/v2
---

<!-- 💡【Stage 0 架构师通用指南（填写后可删除本注释）】
     本模板用于记录重要物品、传世信物、核心资料、专属装备或关键道具，适配全题材：
     - 言情/都市：传家信物、定制腕表、核心商业私密文件、专属座驾、珍贵纪念物；
     - 悬疑/刑侦：关键物证、加密存储介质、特制侦查装备、陈年绝密档案；
     - 玄幻/科幻/历史：宗门至宝、飞舟机甲、虎符遗诏、高维科技芯片。
     ★ 规范：重要物品明确归属人与流转过程，未定细节均可写“自行设定”。 -->

# {{slot:item_name|道具/装备/信物/物品名}}

---

## 一、 基础档案与品阶定位

- **物品全称与常见别名**：{{slot:item_name}}（别名：{{slot:item_aliases|如：传世古玉 / 绝密黑匣 / 龙纹佩（自行设定）}}）
- **品阶评定与稀有度（Tier Rank & Name）**：{{slot:item_tier_name}}（Tier Rank: {{slot:item_tier_rank|3}} ｜ {{slot:item_scarcity|珍贵罕见 / 独一无二 / 专属定制（自行设定）}}）
- **当前合法持有者**：**{{slot:item_holder}}**
- **存放位置与状态**：{{slot:item_location|随身佩戴 / 随身公文包 / 安全保险箱（自行设定）}}

---

## 二、 外观材质与感官特征（Sensory Anchor）

- **材质、色泽与微观质感**：
  {{slot:item_material|例如：温润微凉的羊脂白玉、表面有细致暗纹 / 哑光金属外壳、工艺极精（自行设定）}}
- **尺寸、重量与辨识细节**：
  {{slot:item_size_weight|例如：小巧便携、握在掌心极有分量、做工严密扎实（自行设定）}}
- **感官物象总结（Sensory Anchor）**：
  {{slot:item_sensory_anchor|特征鲜明、辨识度极高（自行设定）}}

---

## 三、 核心功能与使用规则（Function & Depletion）

- **核心功能 / 实际价值**：
  {{slot:item_main_power|发挥关键凭证作用 / 解决核心专业难题 / 具有重大象征意义与价值（自行设定）}}
- **使用条件与维护要求（Cost Per Use）**：
  {{slot:item_cost_per_use|需要专属授权、专业操作或妥善保养（自行设定）}}
- **使用状态与损耗（Charges & Durability）**：
  - 剩余可用次数/充能：{{slot:item_charges|10}} / 上限：{{slot:item_max_charges|10}}（常驻物品可写“常驻使用”）
  - 成色与磨损状态：{{slot:item_durability|完好无损 / 保存良好（自行设定）}}

---

## 四、 流转与变迁轨迹（Lifecycle Ledger）

- [初始获得] 第 {{slot:item_obtain_ch|1}} 章：{{slot:item_obtain_event|故事开局阶段获得、家族传承或重要契机中到手（自行设定）}}；
- [后续演变] 第 {{slot:item_evolve_ch|8}} 章：{{slot:item_evolve_event|发挥关键作用或迎来重要升华/改装（自行设定）}}；

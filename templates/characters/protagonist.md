---
id: {{slot:protagonist_id|p_001}}
name: "{{slot:protagonist|主角名}}"
type: person
role: protagonist
tier_rank: {{slot:protagonist_tier_rank|1}}
tier_name: "{{slot:protagonist_tier_name|初始实力阶层/职级称号}}"
power_benchmark: "{{slot:protagonist_power_benchmark|核心表现力实物标尺}}"
faction: "{{slot:protagonist_faction|所属初始势力/阵营}}"
sensory_anchor: "{{slot:protagonist_sensory_anchor|标志性穿戴与视觉记忆物象}}"
status: active
address_matrix:
  "{{slot:target_char_1|核心搭档或第一女配名}}": "{{slot:addr_to_target_1|对方称呼}}"
schema_version: novel-studio.character/v2
---

<!-- 💡【Stage 0 架构师指南（填写后可删）】
     主角是一本书的灵魂与第一发动机。主角卡不是简单的简历，而是全书防吃书、防降智的物理矫正器！
     ★ 全题材适配规范：
       - 玄幻/仙侠：万古大能苏醒/逆天改命者，填境界层级、本命真宝、至尊肉身、锁定称谓「公子」；
       - 都市/商战：金融巨鳄/隐世兵王/超级宗师，填职级资本身家、贴身器械、标志风衣名表、锁定称谓「陆先生/老大」；
       - 科幻/星际：基因超体/星舰领航员/智械先驱，填代际军衔、外骨骼脉冲、机动光刃、锁定称谓「指挥官/长官」；
       - 历史/权谋：贬谪帝师/寒门谋主/边军统帅，填爵位官品、旧羊皮裘紫毫笔、佩剑虎符、锁定称谓「先生/九爷」。
     ★ 状态对齐：YAML Front-matter 中的 id, name, type, role, tier_rank (1-12), tier_name, power_benchmark, faction, sensory_anchor, status, address_matrix 均已与 实体四表（persons/items/factions/places） 法定 Schema 100% 闭环对齐！ -->

# {{slot:protagonist|主角名}}

## 基础外貌与感官伪装档案（Sensory Profile）

- **真实身份与核心底蕴**：
  {{slot:mc_true_identity|【玄幻】万年太古禁忌混沌神尊 / 【都市】掌控万亿暗流的离岸资本操盘手 / 【科幻】第三纪元最后一位超弦领航员 / 【历史】先帝密诏托孤帝师}}
- **当前外在处境与伪装身份**：
  {{slot:mc_apparent_identity|【玄幻】初醒重伤修士 / 【都市】市井旧书店老板 / 【科幻】废弃空间站拾荒散修 / 【历史】边陲驿丞}}
- **容貌特征与标志性物象（Sensory Anchor）**：
  {{slot:protagonist_sensory_anchor|例如：一袭略显陈旧的素白长袍，左手食指佩戴一枚无光暗金古戒，指节修长沉稳}}

---

## 核心心理四维与绝对逆鳞（Psychological Engine）（仅为示例，灵活填写）

- **Want（表面最强烈直接的欲望目标）**：
  {{slot:mc_want|解决眼前危机、夺回核心王牌、横扫当前阻碍、踏破既得利益阻网}}
- **Need（深层真正灵魂渴求与心智成长）**：
  {{slot:mc_need|打破宿命因果轮回、守护身边真正托付信任之人、重塑失衡公理}}
- **Fear（内心最深处的恐惧与软肋）**：
  {{slot:mc_fear|重要伙伴因自身力量不及而再次湮灭、重蹈旧日万劫不复的覆辙}}
- **Lie（曾经深信不疑却被现实撕碎的认知）**：
  {{slot:mc_lie|曾以为妥协克制能换来和平 / 曾以为一人独行即可背负天下}}
- **绝对逆鳞（触之必死之红线）**：
  {{slot:mc_redline|身边的生死同伴与至亲绝不可触碰，任何拿人质施压者必受连根拔起的雷霆反噬！}}

---

## 实力配置、物理实物标尺与杀手锏（Power & Benchmarks）

- **当前真实实力境界/层级（Tier Name）**：
  {{slot:protagonist_tier_name|例如：气脉境九重（但神识与肉身强度可跨大阶碾压通玄后期）}}
- **标准化位阶数字（Tier Rank）**：
  {{slot:protagonist_tier_rank|1}}（1~12阶标准标尺，卷一立足期通常为 1~2）
- **核心破坏力/影响力实物标尺（Power Benchmark）**：
  {{slot:protagonist_power_benchmark|【玄幻】随手挥袖震碎千斤青石、音波震退十步；【都市】单日调动千万筹码封死跌停板；【科幻】脉冲光刃切断三层纳米装甲；【历史】密信一封调遣八百铁骑封城}}
- **随身王牌装备与资产**：
  {{slot:mc_weapons|随身核心道具/信物/兵刃（须与 entities/items 中的卡片相对应）}}
- **底牌绝杀（致命王牌）**：
  {{slot:mc_trump_cards|不到万不得已不轻露的底牌，一旦祭出必定清场灭口}}
- **交锋风格美学**：
  出手狠辣精准，绝无多余前摇口嗨；善于利用纯粹力量形变与极速物理碾压，干净利落。

---

## 习惯微动作与神态库（去冷脸专属动作指令）（仅为示例，灵活填写）

<!-- Stylist 与 Editor 必须在此提取专属微动作，严禁全篇机械复读“神色淡然、面无表情”： -->

- **从容/运筹帷幄时**：{{slot:mc_act_calm|自行设定}}
- **动怒/杀意浮现时**：{{slot:mc_act_angry|自行设定}}
- **戏谑/看待小丑挑衅时**：{{slot:mc_act_irony|自行设定}}
- **温和/对待信任伙伴时**：{{slot:mc_act_warm|自行设定}}
- **（自行列举更多情景）**

---

## 恒定称谓与人际矩阵（全书恒定防吃书 · 规范）（仅为示例，灵活填写）

<!-- ★ 核心对账字典：正文中所有称谓必须与本表 100% 严格一致，严禁私自漂移！ -->

- **自我称谓（自称）**：
  - 对外人 / 敌人 / 普罗大众：「{{slot:mc_self_public|本尊 / 我}}」
  - 对亲密伙伴 / 私下相处：「我」
  
- **对关键人物称谓（唯一指定锁定）**：
  - 对{{slot:target_char_1|核心搭档或第一女配名}}：「{{slot:mc_addr_to_target_1|对方称呼}}」
  - 对后生晚辈：平淡直呼其名，或称「小辈」
  - 对反派小丑：直呼其名，或称「蝼蚁」
  
- **他人对主角称谓（绝对锁定）**：
  - {{slot:target_char_1|核心搭档或第一女配名}}称呼本角色：「{{slot:target_1_addr_to_mc|主角称呼}}」
  - 门人下属称呼本角色：「{{slot:subordinates_addr_to_mc|太上神尊 / 先生 / 长官}}」
  - 敌对势力称呼本角色：「{{slot:enemies_addr_to_mc|狂徒 / 神秘人 / 阁下}}」

---

## 变迁与成长里程碑台账（动态演变跟踪）

<!-- 供 Stage 4 Reader 提案与 Stage 5 Sync 记录主角的不可逆重大节点： -->

- [初始状态] {{slot:mc_init_milestone|自神棺中苏醒 / 接受破产烂摊子 / 降临空间站底舱 / 自行设定其它}}，底蕴初步激活；

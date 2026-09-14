---
id: {{slot:protagonist_id|p_001}}
name: "{{slot:protagonist|主角名}}"
type: person
role: protagonist
tier_rank: {{slot:protagonist_tier_rank|1}}
tier_name: "{{slot:protagonist_tier_name|初始实力阶层/职级称号}}"
power_benchmark: "{{slot:protagonist_power_benchmark|核心表现力实物标尺}}"
faction: "{{slot:protagonist_faction|所属初始势力/阵营/机构}}"
sensory_anchor: "{{slot:protagonist_sensory_anchor|标志性穿戴与视觉记忆物象}}"
status: active
address_matrix:
  "{{slot:target_char_1|核心搭档或第一女配/男配名}}": "{{slot:addr_to_target_1|对方称呼}}"
schema_version: novel-studio.character/v2
---

<!-- 💡【Stage 0 架构师通用指南（填写后可删除本注释）】
     主角是全书的灵魂与第一推动力，本卡确立主角的核心档案、心理四维与言行标尺，适配全题材：
     - 言情/都市：职场身份/背景、外貌气质、心理诉求、习惯微动作与专属称谓；
     - 悬疑/刑侦：探案专长、敏锐洞察、办案风格、性格软肋与执念；
     - 玄幻/科幻/历史：实力位阶、本命道具/信物、核心底牌与人际矩阵。
     ★ 规范：称谓与关键属性一旦确立，后置工序保持一致，未定内容均可写“自行设定”。 -->

# {{slot:protagonist|主角名}}

---

## 一、 基础外貌与感官档案（Sensory Profile）

- **真实身份与核心背景**：
  {{slot:mc_true_identity|【言情/都市】海归建筑设计师 / 隐秘投资人 / 律所合伙人；【玄幻/科幻】隐世大能转世 / 顶尖领航员 / 传承者（自行设定）}}
- **当前外在处境与表层身份**：
  {{slot:mc_apparent_identity|【言情/都市】初入职场的新人 / 街角花店老板 / 基层职员；【玄幻/科幻】初醒散修 / 拾荒者（自行设定）}}
- **容貌特征与标志性物象（Sensory Anchor）**：
  {{slot:protagonist_sensory_anchor|例如：身着简约白衬衫、戴一副细黑框眼镜、眼神清澈专注 / 标志性风衣与随身信物（自行设定）}}

---

## 二、 核心心理四维与底线原则（Psychological Engine）

<!-- 💡 心理四维驱动人物做出符合人性的决策（自由设定）： -->

- **Want（表面最直接的愿望与目标）**：
  {{slot:mc_want|解决眼前的现实难题、立足当下环境、完成当前关键项目/目标（自行设定）}}
- **Need（深层真正的心灵渴求与成长）**：
  {{slot:mc_need|解开过往心结、收获真挚信任与情感羁绊、实现自我价值（自行设定）}}
- **Fear（内心深处的担忧与软肋）**：
  {{slot:mc_fear|失去珍视之人、辜负信任、重蹈过去的遗憾（自行设定）}}
- **Lie（曾经执拗或有偏差的认知谎言）**：
  {{slot:mc_lie|曾以为独自承担就能解决一切 / 曾对亲密关系心怀防备（自行设定）}}
- **绝对底线 / 逆鳞**：
  {{slot:mc_redline|身边珍视之人与原则底线绝不容践踏，触碰必将果断反击（自行设定）}}

---

## 三、 能力配置、表现力标尺与核心底牌（Power & Benchmarks）

- **当前实力/职级/层级（Tier Name）**：
  {{slot:protagonist_tier_name|例如：资深设计师 / 部门主管 / 气脉境初期 / 注册执业者（自行设定）}}
- **标准化位阶数字（Tier Rank）**：
  {{slot:protagonist_tier_rank|1}}（1~12阶标准标尺，卷一立足期通常为 1~2）
- **核心能力/业务表现力标尺（Power Benchmark）**：
  {{slot:protagonist_power_benchmark|专业领域卓越洞察、高效解决复杂问题、关键时刻力挽狂澜的实力表现（自行设定）}}
- **随身核心道具/信物/工具**：
  {{slot:mc_weapons|随身专属工具、信物、核心资料或关键物品（自行设定）}}
- **核心底牌（关键王牌）**：
  {{slot:mc_trump_cards|不到关键时刻不轻易显露的核心技能、深层人脉或独家底牌（自行设定）}}
- **行事与处事风格**：
  行事沉稳利落，条理清晰；面对挑战冷静果断，对待同伴真诚有担当。

---

## 四、 习惯微动作与神态库（去脸谱化专属细节）

<!-- 💡 提取具有辨识度的生活化微动作，拒绝千篇一律的冷脸面瘫： -->

- **从容/专注思考时**：{{slot:mc_act_calm|自行设定（如：下意识轻推眼镜、手指轻叩桌面、神情专注而沉静）}}
- **严肃/动怒表明立场时**：{{slot:mc_act_angry|自行设定（如：目光骤然凝聚、语调沉稳笃定不容置疑）}}
- **轻松/幽默调侃时**：{{slot:mc_act_irony|自行设定（如：眉梢微挑、唇角浮现一抹淡淡笑意）}}
- **温和/对待亲近之人时**：{{slot:mc_act_warm|自行设定（如：眼神柔和、语气舒缓自然、动作体贴周到）}}
<!-- （可按需自由补充更多情景动作） -->

---

## 五、 恒定称谓与人际矩阵（全书称谓对账基准）

<!-- 💡 锁定核心称谓，确保正文对话与叙述严谨自洽： -->

- **自我称谓（自称）**：
  - 对外人 / 正式场合：「{{slot:mc_self_public|我 / 本人 / 在下}}」
  - 对亲密之人 / 私下相处：「我」
  
- **对关键人物称谓（锁定基准）**：
  - 对{{slot:target_char_1|核心搭档或第一女配/男配名}}：「{{slot:mc_addr_to_target_1|对方称呼（如：晚晚 / 林总 / 师妹）}}」
  - 对下属/晚辈：直呼其名或随和称呼
  - 对竞争对手：直呼其名或礼貌客套称谓
  
- **他人对主角称谓（锁定基准）**：
  - {{slot:target_char_1|核心搭档或第一女配/男配名}}称呼主角：「{{slot:target_1_addr_to_mc|主角称呼（如：陆工 / 师兄 / 名字）}}」
  - 同事/下属称呼主角：「{{slot:subordinates_addr_to_mc|老大 / 陆先生 / 队长}}」
  - 对手/外部人士称呼主角：「{{slot:enemies_addr_to_mc|陆总 / 阁下 / 直呼姓名}}」

---

## 六、 变迁与成长里程碑台账（动态演变追踪）

- [初始状态] {{slot:mc_init_milestone|故事开篇处境，开启新阶段旅程或初遇核心人物（自行设定）}}

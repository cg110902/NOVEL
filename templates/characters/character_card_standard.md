---
id: {{slot:char_id|p_002}}
name: "{{slot:char_name|角色名}}"
type: person
role: {{slot:char_role|deuteragonist|主配角/女主/男配/主要反派/关键盟友}}
tier_rank: {{slot:char_tier_rank|2}}
tier_name: "{{slot:char_tier_name|当前实力层级/职级称号}}"
power_benchmark: "{{slot:char_power_benchmark|核心破坏力与实物标尺}}"
faction: "{{slot:char_faction|所属阵营/机构/势力}}"
sensory_anchor: "{{slot:char_sensory_anchor|容貌体态与标志性物象}}"
status: active
address_matrix:
  "{{slot:protagonist|主角名}}": "{{slot:addr_to_mc|对主角称呼}}"
schema_version: novel-studio.character/v2
---

<!-- 💡【Stage 0 架构师通用指南（填写后可删除本注释）】
     本模板是重要配角、关键搭档、女主角、对手或导师的标准模板。
     复制至 characters/<角色名>.md 并填实。
     ★ 规范：称谓与人物动机一旦确立保持前后一致，未定内容均可写“自行设定”。 -->

# {{slot:char_name|角色名}}

---

## 一、 基础档案与外貌感官特征（Sensory Profile）

- **核心身份与社会定位**：
  {{slot:char_identity|例如：主治医师 / 投行总监 / 宗门圣女 / 专案组核心探员（自行设定）}}
- **初登场章节与情境**：
  {{slot:char_first_appear|例如：第 1 章，在开篇事件或特定工作场所与主角初识（自行设定）}}
- **容貌体貌与标志性物象（Sensory Anchor）**：
  {{slot:char_sensory_anchor|例如：身着干练浅色风衣、长发挽起、眼神敏锐沉静 / 标志性随身配饰（自行设定）}}

---

## 二、 核心欲望与心理机制（Psychological Engine）

- **Want（当前核心欲望与首要目标）**：
  {{slot:char_want|解决眼前危机 / 完成关键项目 / 探寻某个真相 / 守护重要事物（自行设定）}}
- **Need（深层真正的心灵渴求与成长）**：
  {{slot:char_need|获得真正的认可、解开内心束缚、找到志同道合的同行者（自行设定）}}
- **Fear（心底最深恐惧与致命软肋）**：
  {{slot:char_fear|重蹈过去的失败覆辙、失去重要之人的信任（自行设定）}}
- **核心动机（驱动其行动的内在火种）**：
  {{slot:char_motive|强烈的责任感、对专业的执着、或对至亲的守护信念（自行设定）}}
- **底线原则（不可逾越的红线）**：
  {{slot:char_redline|职业道德底线、身边同伴的安全与人格尊严不可侵犯（自行设定）}}

---

## 三、 恒定称谓与人际矩阵（全书称谓基准）

- **自我称谓（自称）**：
  - 私下 / 对主角时：{{slot:addr_self_private|「我」}}
  - 对外 / 正式场合：{{slot:addr_self_public|「我」 / 「在下」 / 「本人」}}
  
- **对关键人物称谓（唯一指定）**：
  - 对{{slot:protagonist|主角名}}：「{{slot:addr_to_mc|称谓（如：名字 / 职务 / 昵称）}}」
  - 对同事 / 同门：{{slot:addr_to_subordinates|礼貌得体，直呼其名或职务}}
  - 对竞争对手 / 敌对者：{{slot:addr_to_enemies|冷淡疏离，礼貌客套或直呼全名}}
  
- **他人对本角色称谓（绝对锁定）**：
  - {{slot:protagonist|主角名}}称呼本角色：「{{slot:mc_addr_to_char|主角对该角色的称呼}}」
  - 同事/内部称呼本角色：「{{slot:faction_addr_to_char|职务称号或名字}}」
  - 外部/对手称呼本角色：「{{slot:enemies_addr_to_char|职务称号或全名}}」

<!-- （可按需自由补充更多称谓条目） -->

---

## 四、 性格特质与言语声线（性格魅力）

- **核心性格特质**：
  {{slot:char_personality|外表沉着干练，内心细腻有温度；有决断力，重情义（自行设定）}}
- **说话口吻与台词特点**：
  {{slot:char_voice|语调清晰利落，条理分明；私下交流时自然温和（自行设定）}}

---

## 五、 习惯微动作与神态库（去脸谱化细节）

- **专注/思考时**：{{slot:char_act_shy|自行设定（如：下意识转动指尖的笔、神情沉静专注）}}
- **警觉/面对挑战时**：{{slot:char_act_alert|自行设定（如：坐直身姿、眼神变得锐利笃定）}}
- **动容/真诚沟通时**：{{slot:char_act_grateful|自行设定（如：目光柔和、流露出真挚微笑）}}
<!-- （可按需自由补充更多情景动作） -->

---

## 六、 能力配置与关键道具

- **实力层级 / 职级（Tier Rank & Name）**：
  {{slot:char_tier_name|职级或实力称号}}（Tier Rank: {{slot:char_tier_rank|2}}）
- **能力表现力实物标尺（Power Benchmark）**：
  {{slot:char_power_benchmark|专业领域核心能力与实战/业务表现（自行设定）}}
- **特殊技能 / 核心专长**：
  {{slot:char_special_power|例如：顶尖刑侦推理 / 高端算法开发 / 独到商业洞察（自行设定）}}
- **随身物品与信物**：
  {{slot:char_items|例如：专属工作设备、随身信物或关键资料（自行设定）}}
- **风格与优势领域**：
  擅长特定领域的统筹与深度分析，与主角形成良好互补。

---

## 七、 与主角关系及演进轨迹

- **与主角核心关系定性**：
  {{slot:char_relation_mc|并肩作战的核心搭档 / 默契同行者 / 惺惺相惜的知己（自行设定）}}
- **重要里程碑记录**：
  - [初始节点] 第 {{slot:char_init_ch|1}} 章：{{slot:char_init_event|故事开局阶段初识，建立初步联系与合作基础（自行设定）}}；

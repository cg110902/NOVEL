---
id: {{slot:char_id|p_002}}
name: "{{slot:char_name|角色名}}"
type: person
role: {{slot:char_role|deuteragonist|主配角/女主/主要反派/忠实盟友}}
tier_rank: {{slot:char_tier_rank|2}}
tier_name: "{{slot:char_tier_name|当前实力层级/职级称号}}"
power_benchmark: "{{slot:char_power_benchmark|核心破坏力与实物标尺}}"
faction: "{{slot:char_faction|所属阵营/势力}}"
sensory_anchor: "{{slot:char_sensory_anchor|容貌体态与标志性物象}}"
status: active
address_matrix:
  "{{slot:protagonist|主角名}}": "{{slot:addr_to_mc|公子}}"
schema_version: novel-studio.character/v2
---

<!-- 💡【Stage 0 架构师指南（填写后可删）】
     本模板是除主角外的所有重要角色（核心配角、核心反派宿敌、忠诚副手、宗门巨擘）的标准模板。
     复制本模板至 characters/<角色名>.md 并填实。
     ★ 契约规范：YAML Front-matter 中的 tier_rank (1-12)、tier_name、power_benchmark、faction、sensory_anchor、status 与 address_matrix 属于 实体四表（persons/items/factions/places） 法定白名单；role 属于卡片标注，入库四表时仅保留白名单字段；称谓矩阵填定即为全书常量，后置工序严禁吃书！
     ★ 全题材适配：
       - 玄幻/仙侠：宗门圣女/少谷主/魔宗巨擘，填境界位阶、极道体质、锁定称谓「公子/贼子」；
       - 都市/商战：集团千金/刑侦队长/死对头操盘手，填职级资本、专属座驾风衣、锁定称谓「陆先生/林总」；
       - 科幻/星际：护卫副官/行星总督/反抗军头领，填基因序列代差、外骨骼光刃、锁定称谓「长官/头儿」；
       - 历史/权谋：相府千金/锦衣卫千户/敌国策士，填封诰官秩、佩刀服色、锁定称谓「侯爷/九爷」。 -->

# {{slot:char_name|角色名}}

## 基础档案与体貌特征

- **核心身份与社会地位**：
  {{slot:char_identity|例如：水云圣宫圣女 / 焚天神谷少谷主 / 跨国财阀第一继承人 / 边关游击将军}}
- **初登场章节与情境**：
  {{slot:char_first_appear|例如：第 1 章，身负重伤逃入荒古断魂洞 / 第 3 章，跨国并购拍卖会现场}}
- **容貌体貌与辨识物象（Sensory Anchor）**：
  {{slot:char_sensory_anchor|例如：容颜清绝出尘、身披冰蓝云纹罗裙、腰悬一枚冰晶玉佩，眉宇间带着清傲与戒备}}

---

## 核心欲望与心理机制（Psychological Engine）（仅为示例，灵活填写）

- **Want（当前核心欲望与首要目标）**：
  {{slot:char_want|化解体内剧毒/洗刷家族冤屈/肃清派系内奸/夺回被窃资产}}
- **Need（深层真正灵魂渴求与心智成长）**：
  {{slot:char_need|不再依附他人庇护、独当一面守护至亲或道统}}
- **Fear（心底最深恐惧与致命软肋）**：
  {{slot:char_fear|宗门道统在自己手中覆灭/沦为他人玩物傀儡/再次遭到信任之人背叛}}
- **核心动机（驱动其行动的内在火种）**：
  {{slot:char_motive|对家族荣誉与道统的执念，在生死存亡边缘敢于孤注一掷的决绝骨气}}
- **绝对逆鳞（不可逾越的底线/触之必死之雷区）**：
  {{slot:char_redline|身边的生死同伴、至亲至爱与宗门最后底线绝不可辱，触者必受疯狂反扑！}}

---

## 恒定称谓与人际矩阵（全书恒定防吃书 · 核心审校区）（仅为示例，灵活填写）

<!-- ★ 规范：本表为 Auditor 仲裁与 Editor 审校的核心依据，任何正文违规称谓直接标红！ -->

- **自我称谓（自称）**：
  - 私下 / 对主角时：{{slot:addr_self_private|「我」 / 「称谓」}}
  - 对外 / 正式场合：{{slot:addr_self_public|「本圣女」 / 「本少主」 / 「在下」 / 「鄙人」}}
  
- **对关键人物称谓（唯一指定 · 严禁擅改）**：
  - 对主角：「{{slot:addr_to_mc|公子}}」
  - 对同门 / 下属：{{slot:addr_to_subordinates|平辈互称师兄妹，对下属从容令下}}
  - 对死敌 / 背叛者：{{slot:addr_to_enemies|冷酷直呼其名，或斥为“叛徒”、“狂徒”}}
  
- **他人对本角色称谓**：
  - 主角对本角色称谓：「{{slot:mc_addr_to_char|称谓}}」 或 「{{slot:mc_addr_to_char_alt|称谓}}」
  - 内部成员/同门称谓：{{slot:faction_addr_to_char|「圣女殿下」 / 「萧师妹」 / 「林总」}}
  - 敌对势力/外界称谓：{{slot:enemies_addr_to_char|「水云圣女」 / 「妖女」 / 「那个疯女人」}}
  
  **（更多补充）**

---

## 性格特质与台词声线（仅为示例，灵活填写）

- **核心性格特质**：
  {{slot:char_personality|外冷内热，骨子里极硬；危急时刻极具决断力；对真正认准之人死心塌地、敢作敢当}}
- **说话口吻与台词声线**：
  {{slot:char_voice|语调利落清爽，字句清晰，绝不说模棱两可的废话；在主角面前偶尔流露出微嗔与羞怯}}

---

## 习惯微动作与神态库（拒绝千人一面 · 去冷脸专属）（仅为示例，灵活填写）

<!-- Stylist 与 Editor 必须在此提取专属微动作，严禁全篇机械复读“神色淡然、面无表情”： -->

- **害羞/慌乱时**：{{slot:char_act_shy|下意识微咬下唇，长睫微颤，视线快速避开}}
- **戒备/拔剑时**：{{slot:char_act_alert|右手五指骤然扣住剑柄或掌心蓄力，周身气场骤冷}}
- **动容/感激时**：{{slot:char_act_grateful|双手交叠欠身施礼，神色由紧绷彻底转为真诚托付}}
- **（补充更多情景动作）**

---

## 实力配置、物理标尺与关键道具

- **实力层级（Tier Rank & Name）**：
  {{slot:char_tier_name|通玄境后期}}（Tier Rank: {{slot:char_tier_rank|2}}）
- **破坏力/影响力实物标尺（Power Benchmark）**：
  {{slot:char_power_benchmark|一剑斩断合抱古木、寒霜剑气封冻百丈潭水}}
- **特殊体质 / 核心技能机制**：
  {{slot:char_special_power|例如：极道水灵体、九天玄水诀 / 顶级量子加密黑客技术}}
- **随身武器与关键道具**：
  {{slot:char_items|例如：秋水玄冰剑（三阶灵宝）、水灵神珠（本命传承信物）}}
- **战斗风格与局限**：
  擅长远程控场与剑气杀伐，贴身纯肉搏力量稍逊。

---

## 与主角关系及不可逆演进轨迹

- **与主角核心关系定性**：
  {{slot:char_relation_mc|命中注定的第一道侣 / 生死交付的商业合伙人 / 唯一能托付后背的副手}}
- **不可逆重大里程碑记录**：
  - [初始节点] 第 {{slot:char_init_ch|1}} 章：{{slot:char_init_event|断魂洞绝境与主角结识并结下深层契约羁绊}}；

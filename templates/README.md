# templates/ — 全题材底层词典与设定规范库（Canonical Lore & Correction Templates）

本目录是 Novel Studio 的**全题材底层世界观、实体知识库与对账规范模板库**。
不仅是一次性脚手架，更是全书在 Stage 0 筑基后沉淀为 10,000~20,000+ 字字全景物理定律的**底层词典与机械矫正器**。后续全流水线的增删改查对账均以此为基准锚点。


**【Architect 填写注意事项】**：

模板中的预填信息仅为占位，请根据当前题材与设定灵活填写，可自行补充更多！

---

## 目录与模块全景架构

```text
templates/
├── project.json                   # 全题材通用词表种子配置（含停用词、防AI套话、伤残监测等高灵敏度探针）
├── beats.md                       # 单章细纲任务书模板（含反套路推演、场景脉络、法定事实清单、交付契约）
├── bible/                         # 全书世界观与运转公理词典模块（Stage 0 深度筑基）
│   ├── 01_world_axioms.md         # 世界底色、底层公理与运转机制（含金手指运转逻辑）
│   ├── 02_power_system.md         # 阶层/实力梯阶与物理/社会实物标尺（防表现力通胀）
│   ├── 03_factions_geography.md   # 地缘区划、各方势力矩阵与利益冲突拓扑
│   ├── 04_economy_items.md        # 经济通货、购买力锚点与物资道具品阶
│   ├── 05_special_mechanics.md    # 特殊机制、体质/血脉/职业谱系与代偿惩戒法则
│   ├── 06_style_guidelines.md     # 文风基线、微动作多样性库（防冷脸）
│   └── 07_deviations.md           # 本书偏离清单与核心创作红线（推翻传统套路声明）
├── characters/                    # 角色全息卡模板
│   ├── protagonist.md             # 主角高维专属全息卡（含万古底蕴、心理四维、防冷脸微动作、绝对称谓矩阵）
│   └── character_card_standard.md # 标准重要角色/女主/宿敌全息卡模板
├── entities/                      # 非人物类实体全息卡模板（彻底终结道具势力无卡裸奔顽疾）
│   ├── item_card.md               # 核心资产/装备/道具/载具卡模板（品阶、材质物象、能耗代价、充能流转）
│   ├── faction_card.md            # 核心势力/宗门/组织卡模板（权力架构、镇派底蕴、敌友网络、变迁轨迹）
│   └── location_card.md           # 关键地标/秘境/场景卡模板（空间氛围、感官细节、环境法则、历史节点）
└── outlines/                      # 全书与分卷剧情大纲模板
    ├── main_plot.md               # 全书主线脊柱与长程宏观架构（开局/终局/动力引擎/里程碑）
    └── volume_outline.md          # 分卷大纲模板（本卷承诺、主冲突驱动力、四分位阶段规划、埋还线清单）
```

---

## 模板实例化与目标路径对照

| 模板源文件 | `studio.py init` 目标路径 | 负责角色 | 核心功能与引擎联动 |
|---|---|---|---|
| `project.json` | `project.json` | 引擎自动 | **20 个顶层键**：建档元数据 + 引擎旋钮（`words_target`/`lines_cap`/`audit_mode`/`tier_shift_grace`/`voiceprint`/`reader_memory`/`state_watch`）+ 取证词表 + **六张题材词表**（脚手架带跨题材兜底种子，Architect 须按本书题材**重写**；缺席＝该档停用、`[]`＝明确关闭。供参流程：`config guide` → `config suggest` → `config set <键> --merge`） |
| `bible/01_world_axioms.md` | `bible/01_world_axioms.md` | Architect | 世界底层物理与逻辑公理，金手指运转机制 |
| `bible/02_power_system.md` | `bible/02_power_system.md` | Architect | 力量/社会地位实物标尺，默认恒给 `pack` P0；细纲声明 `world_refs` 后改为按章取用 |
| `bible/03_factions_geography.md` | `bible/03_factions_geography.md` | Architect | 地缘版图与势力利益冲突拓扑，默认恒给 `pack` P0（同上，可被 `world_refs` 收窄） |
| `bible/04_economy_items.md` | `bible/04_economy_items.md` | Architect | 货币购买力平价锚点，道具品阶与损耗充能账本 |
| `bible/05_special_mechanics.md` | `bible/05_special_mechanics.md` | Architect | 独家机制、体质相生相克与反噬走火入魔代偿法则 |
| `bible/06_style_guidelines.md` | `bible/06_style_guidelines.md` | Architect | 通俗直白大白话规范、微表情多样性库 |
| `bible/07_deviations.md` | `bible/07_deviations.md` | Architect | 本书偏离清单（`pack` 强制提取注入 P0 时空胶囊） |
| `characters/protagonist.md` | `characters/protagonist.md` | Architect | 主角全息卡（含绝对称谓矩阵）；卡是**人读视图**，称谓基准由主控抄进细纲、由 `pack` 从台账侧注入 |
| `characters/character_card_standard.md` | 按需手工复制到 `characters/<角色名>.md` | 主控 / Architect | 重要角色/女主/宿敌全息卡（锁定法定称谓对账表） |
| `entities/item_card.md` | 按需手工复制到 `entities/items/<道具名>.md` | 主控 / Architect | 核心道具/装备/神舟卡（追踪充能、持有者流转） |
| `entities/faction_card.md` | 按需手工复制到 `entities/factions/<势力名>.md` | 主控 / Architect | 核心势力卡（组织架构与对外关系） |
| `entities/location_card.md` | 按需手工复制到 `entities/locations/<地名>.md` | 主控 / Architect | 核心地标与第一案发现场空间格局 |
| `outlines/main_plot.md` | `outlines/main_plot.md` | Architect | 全书主线脊柱、核心三幕与长线里程碑 |
| `outlines/volume_outline.md` | `outlines/vol_01/outline.md` | Architect | 首卷分卷大纲与四分位剧情航标 |
| `beats.md` | `studio.py beats new [章节] --write` 自动装配生成（`beats` 只有 `new` 一个子命令；在场人册来自 `state/current.json.present_characters`，注入速查节） | 主控 (Director) | 单章细纲任务书（反套路推演、场景脉络、法定事实对校）；选填 `world_refs` 决定本章取用哪些 bible 锚点 |

---

## 填写、增删改查与生命周期规范

1. **Stage 0 深度筑基规范**：
   - 执行 `python studio.py init -w workspace/<书名> -t "书名" -g "题材" -p "主角名"` 后，模板自动全量实例化；
   - 由 `Architect`（架构师）在独立纯净沙盒中完成全部 `{{slot:...}}` 的深度填充，字数规模应达到 **10,000~20,000+ 字**；
   - 填实后运行 `python studio.py check`，未填槽位将由 `unfilled_slot` 闸门机械拦截。

2. **全局统一物理 ID 编码前缀矩阵 (Canonical Entity ID Matrix)**：
   全书所有实体均拥有全生命周期不可变唯一物理 ID，作为底层持久化与跨章精准检索键：
   - 👤 **角色 (person)**：`p_001`（主角恒定为 `p_001`）, `p_002`, `p_003`...
   - ⚔️ **物品与法宝 (item)**：`it_001`, `it_002`, `it_003`...
   - 🏰 **势力与组织 (faction)**：`fac_001`, `fac_002`, `fac_003`...
   - 🗺️ **地点与关节点 (location)**：`loc_001`, `loc_002`, `loc_003`...

3. **二八实体分级管理法则 (Tiered Entity Management)**：
   彻底杜绝长篇小说中“路人甲都要建个卡片”导致的千张碎卡爆炸灾难：
   - 🌟 **核心实体（占 20%，决定 80% 叙事）**：主角、核心女主、长线宿敌、宗门重臣、本命重器、首府要塞。
     - **标准**：必须在 `characters/` 或 `entities/` 建立独立的 `.md` 全息卡，锁定称谓矩阵、Want/Fear 与物象；
     - **台账**：在 `实体四表（persons/items/factions/places）` 中配置对应 `card: "characters/<名字>.md"` 路径。
   - 🍃 **次要/临时实体（占 80%，服务即时情节）**：客栈掌柜、巡逻守卫、传话执事、临时消耗符箓、路过村庄。
     - **标准**：**坚决不建 `.md` 冗余卡片**，避免文件污染与磁盘膨胀；
     - **台账**：直接由 Reader 在 Stage 4 提案中登记入 `实体四表（persons/items/factions/places）`（设置 `card: ""`），记录其姓名、ID、境界、阵营与正文引文即可。

4. **强类型物理通用字段（Entities Schema 核心白名单）**：
   底层状态表 `实体四表（persons/items/factions/places）` 开启了 `"additionalProperties": false` 强类型闸门。各角色向状态表登记实体时，**必须严格使用以下法定字段**：
   - 🆔 **标识与类型**：
     - `id`: 唯一物理 ID（终身不可变：`p_001`, `it_001`, `fac_001`, `loc_001`）
     - `name`: 实体中文法定全名（唯一主键）
     - `type`: 实体类型（严格枚举：`person`, `item`, `location`, `place`, `faction`, `other`）
     - `aliases`: 别名、代号、尊号列表（`array[str]`）
     - `card`: 对应全息卡相对路径（核心实体如 `"characters/主角.md"`，次要路人留空 `""`）
     - `summary`: 实体一句话核心定位（`str`）
   - ⚡ **战力与位阶（防通胀标尺）**：
     - `tier_rank`: 实力/品阶梯阶整数（`1 ~ 12` 级，用于侧对侧数值对比）
     - `tier_name`: 境界/职级法定称号（如 `"通玄境后期"`、`"玄阶中品"`、`"A级"`）
     - `realm`: 修炼大境界划分（`str`）
     - `power_benchmark`: 破坏力与防御物理实物标尺（`str`）
   - 🩺 **生命与存在状态**：
     - `status`: 实体活跃状态（严格枚举：`active` 活跃, `retired` 隐退/沉睡）
     - `life_status`: 生命体生死状态（严格枚举：`alive` 在世, `deceased` 阵亡, `missing` 失踪）
     - `condition`: 肉身或物性状态（如 `"重伤"`、`"经脉受损"`、`"完好"`）
     - `injury_level`: 伤势等级 `0~5`（`0`=无伤，`5`=濒死；人物专用可算字段，建议与 `injury_desc` 同写）
     - `injury_desc`: 伤势文字说明（如 `"左臂骨折"`）
     - `renown`: 声望/悬赏整数值（人物/势力；正=美名，负=恶名/悬赏）
   - 🗺️ **地缘与归属**：
     - `location`: 当前具体所在空间/据点（`str`，严禁用 `current_location`）
     - `faction`: 所属门派、势力或组织名称（`str`）
     - `attitude`: 对主角/阵营的政治态度（严格枚举：`hostile` 敌对, `neutral` 中立, `friendly` 友善, `allied` 结盟，严禁用 `disposition`）
   - ⚔️ **道具与重器专用**：
     - `holder`: 当前实际支配/持有者角色名（`str`，严禁用 `current_owner`）
     - `charges`: 剩余可用充能/催动次数（`int >= 0`；**非计数型道具直接省略本字段**，写 `-1` 会被模型 `ge=0` 拒绝——
       `proposal check`/`sync` 会以「`entities[i].charges` …」的形式逐条点名字段路径，**没有独立错误码**，按路径改即可）
     - `max_charges`: 最大充能上限（`int >= 1`）
     - `cost_per_use`: 单次催动代价/消耗说明（`str`）
     - `durability`: 物理磨损/耐久度（`str`）
   - 🏰 **势力与据点专用**：
     - `scale_tier`: 势力规模梯级（`1 ~ 10`）
     - `core_assets`: 核心垄断王牌资产清单（`array[str]`）
     - `diplomacy`: 势力外交网络映射（`{"势力名": "hostile"|"neutral"|"friendly"|"allied"}`，词表同 `FactionAttitude` 枚举；⚠️ 本字段是自由字符串字典，引擎不校验取值也不会读它做推断，写错枚举值不会报错——请以枚举为准）
     - `danger_tier`: 地点危险系数（`1 ~ 10`）
     - `environment_rules`: 地理环境法则与准入门槛（`array[str]`）
   - 🎭 **感官物象与称谓锁（防冷脸与防吃书）**：
     - `sensory_anchor`: 标志性外观、穿戴、气味与视觉记忆物象（`str`）
     - `micro_actions`: 标志性习惯微动作与神态库（`array[str]`）
     - `address_matrix`: 对特定实体的法定称谓映射（`{"目标名": "我称呼对方"}`）
     - `relations`: 与特定实体的动态张力网络（`[{"target": "角色名", "type": "rival", "desc": "宿敌"}]`）

   > ⚠️ **【重要：Markdown 卡片 vs 数据库状态表分界规范】**：
   > - **Markdown 卡片（`characters/*.md`, `entities/*/*.md`）**：是面向大模型创作的**全息感官档案**，其正文允许有丰富的 Want/Fear、生平轶事、背景设定等自然语言描述；
   > - **数据库状态表（`实体四表（persons/items/factions/places）`）**：是面向确定性引擎的**强类型检索台账**。提案中向 实体四表 写入的字段**必须且仅能来自上述白名单**，严禁私自添加未经 Schema 许可的字段（如 `leader`, `headquarters`, `bound_to` 等），否则会被引擎机械闸门直接拒绝！

5. **长篇增删改查（CRUD）对账机制**：
   - **增（新实体出场）**：在 beats 中声明，核心角色建卡，次要角色免建卡；由 Reader 在提案 实体四表 中分配递增 ID 注册；
   - **删（战死/毁损/退场）**：由 Reader 在提案中附原句引文，登记为 `deceased` 或 `destroyed`，并生成 `state/locked.json` 锁定；
   - **改（境界突破/道具流转/称谓变更）**：通过 beats 声明演进，Reader 提取更新（引擎以 `id` 为第一主键优先索引，即使改名改换品阶也绝不丢失生命周期）；
   - **查（对校核验）**：Auditor 结合细纲预提炼清单、人物卡称谓矩阵与机械探针，逐行对账正文，杜绝任何擅自越级或漂移。

6. **与引擎的三条对账关系（改模板前必读）**：
   - **模板 ↔ JSON Schema 同源**：本目录是字段契约的**人读侧**，机读侧是 `engine/schemas/*.json`
     （由 `python -m engine.models.schema_gen` 从 Pydantic 模型生成，勿手改）；三者（模板 / Pydantic 模型 /
     Schema）任一改动都必须同步其余两个。子代理**不读 schemas**——给它们的当章合同是 `beats new` 注入的
     `### 📐 提案通道与键形状` 小节；`state/inbox/README.md` 面向主控与人类。
   - **表数口径**：`state/*.json` = **十一表**（`ASSERTED_KEYS`，Agent 可写）+ `derived.json`（第十二张，
     引擎派生缓存）；`project.json` 是 **STATE_KEYS 之外**的书级配置表，**不占表号**（表号只编到第十二张）。
     `pack` 只装 6 张表（current / entities / lines / synopsis / timeline / locked）而不是十二表——
     其余表是**账本**，写手不需要看；`--lean` 只给 P0 热层。实体四表（persons/items/factions/places）
     按 kind 物理拆分，`entities/` 目录只是人读投影（pack 走合并读视图）。
   - **装配预算**：`pack` 总量上限 **2W token**，超预算按压缩阶梯由远及近裁（P2 冷索引 → P2 旧章指针 →
     P1 间接关联 → P1 脊柱 → P0 上章余温）；细纲全文 / current / 硬提醒 / 不可逆事实 / 钉住的锚点**永不自动裁**。
   - **`world_refs` 三态语义**（写细纲时按这三态理解，它不是开关）：
     ① 未声明 → **恒给**全部核心锚点节（旧书零改动）；② 声明且命中 → 只装命中节（**refs 最多取前 8 个**，`MAX_WORLD_ANCHOR_REFS`，超出忽略并点名），且当「世界公理 /
     战力标尺 / 势力地理 / 经济品阶 / 特殊机制」某一组在 bible 里存在却没被覆盖时，pack 打印
     ⚠️ 点名缺哪一组（宁提醒不擅自扩注入）；③ 声明但零命中 → **回退恒给**并回列「可钉的节」供照抄。
     **任何一态都不会让 Drafter 看不到世界观**；钉住的节不受 `world_anchor_tokens` 截断，多钉不挤压别的内容。

7. **CLI 底层词典秒级查询工具链 (Studio Lore CLI)**：
   - `python studio.py lore list`：全景列出所有已注册实体的物理 ID、名称与卡片状态；
   - `python studio.py lore entity <id/name>`：按 ID 或名称穿透调阅实体全息档案（EntityEntry 共 36 个字段，按实际填写渲染）；
   - `python studio.py lore compare <idA/nameA> <idB/nameB>`：秒级对校两实体位阶差距与法定互称矩阵；
   - `python studio.py lore scale`：查看阶梯破坏力与实物标尺；
   - `python studio.py lore rules`：查看不可违背的世界物理与设定公理；
   - `python studio.py errcodes <码>`：单码详解（含义 / 触发条件 / 处置处方），`--json` 机读；全表 `errcodes [--level error]`。

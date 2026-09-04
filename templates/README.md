# templates/ — 创作模板库

本目录是创作模板库：其中 **4 份由 `studio.py init` 自动实例化**到书工作区，细纲任务书支持 `studio.py beats new` 自动脚手架生成。

---

## 模板与阶段对照

| 模板文件 | 实例化方式 | 目标路径 | 填写阶段 | 负责角色 | 说明 |
|---|---|---|---|---|---|
| `project_bible.md` | init 自动 | `bible/project_bible.md` | Stage 0 | 主控 | 世界观背景、核心规则与战力实物标尺（其中核心规则、地理与境界标尺会被 pack 自动恒常注入 P0 时空胶囊） |
| `main_plot.md` | init 自动 | `outlines/main_plot.md` | Stage 0 | 主控 | 全书主线脊柱、开局/中继/终局设定 |
| `volume_outline.md` | init 自动（仅 vol_01） | `outlines/vol_XX/outline.md` | Stage 0 / 开新卷 | 主控 | 开新卷时**手工复制改名**（模板已适配 `{{slot:vol_id}}`） |
| `character_card.md` | init 自动（仅主角） | `characters/protagonist.md` | Stage 0 起 | 主控 | 后续角色**手工复制改名**（如 `characters/林编辑.md`——按本书角色自定）；人设卡（Want/Fear、性格与说话风格） |
| `beats.md` | `studio.py beats new [章节] --write` 自动生成 | `outlines/vol_XX/beats/ch_XXX.md` | Stage 1 | 主控 | 单章细纲任务书（自动注入阶段目标、现场情境、到期线索、情绪蓄水泵、通用场景脉络、新面孔速写插槽与交付契约） |
| `reader_review.md` | 手工参考 | 状态提案骨架，落盘为 `state/inbox/ch_XXX.json` | Stage 4 | Reader | **标准增量状态提案骨架 (Proposal Skeleton)**：Reader 客观审计事实后装配为纯 JSON 提案（注：本文件为 .md 承载的 JSON 结构，落盘须存为 .json；勿与 Stage 5 的 `log/review/` 校对注记混淆） |

---

## beats front-matter 合法键清单（引擎强制，超键报错 `beats_fm_extra_keys`）

| 键 | 用途 |
|---|---|
| `chapter` / `vol` | 章号 / 卷号（如 `ch_007` / `vol_01`） |
| `form` | 章型（生死博弈/战后清点/暗流汇聚/危机逼近）；连章同 form 必须给 `form_reason` |
| `form_reason` | 与上一章同 form 的理由声明 |
| `pov` | 视角角色 |
| `words` | 本章自报字数带（如 `2000-2500`，在 `2000-3000+` 自由舒展）；与上一章带差 <400 会触发 `words_band_crowded` 警告 |
| `style_notes` | 风格旋钮（竖线分隔）；禁止与上一章全同（`style_notes_copy` 警告） |
| `editor_extra` | 传递给 Editor 的附加约束 |
| `tension_curve` | 张力曲线宏观描述 |
| `tension_score` | 冲突张力分值（1~10） |
| `stage_mode` | 叙事阶段模式（`Suppression` 蓄水打压 / `Simmering` 试探对峙 / `Eruption` 爆发反杀 / `Harvest` 战后清点） |
| `suppression_factors` | 蓄水模式必填：反派跋扈压制或外部阻碍，严禁主角当场秒杀 |
| `release_trigger` | 决战爆发模式必填：掀开致命底牌或破局绝招瞬间 |

---

## 填写与生命周期规范

1. **槽位填充**：模板中的 `{{slot:xxx}}` 为初始化占位符，完成 Stage 0 设定后填实。`python studio.py check` 会自动检查未填槽位。
2. **细纲智能生成**：Stage 1 推荐直接执行 `python studio.py beats new [章节] --write`，引擎会自动提取大纲规划、上章现场、到期线索并填充通用场景脉络与情绪蓄水模式。
3. **人物卡与实体分级建立机制**：
   - **主要/核心角色**：在 `characters/<角色名>.md` 建立独立人物卡，并在 `state/entities.json` 注册；
   - **次要/临时实体（杂兵/临时道具/背景地点）**：无需手工建卡，由 Stage 4 Reader 自动装配进 `state/inbox/ch_XXX.json`，Stage 5 主控审定后执行 `studio.py sync` 即可自动注册进 `state/entities.json`。
4. **动态细纲任务书格式**：单章 beats 文件头部为 YAML Front-matter（合法键见上表），正文包含 `## 核心冲突与场景脉络`、`## 伏笔与线索动作` 以及 `## 交付契约`（引擎按标题关键字提取这三节，勿改节名结构）。
5. **双轨质检落地**：Stage 4 由 Reader 负责提取事实装配 `state/inbox/ch_XXX.json`，由 Critic 负责老白读者体验评审并输出 `log/critic/ch_XXX.md`。

# templates/ — 创作模板库

本目录是创作模板库：其中 **4 份由 `studio.py init` 自动实例化**到书工作区，**2 份为手工复制/参考模板**。

---

## 模板与阶段对照

| 模板文件 | 实例化方式 | 目标路径 | 填写阶段 | 负责角色 | 说明 |
|---|---|---|---|---|---|
| `project_bible.md` | init 自动 | `bible/project_bible.md` | Stage 0 | 主控 | 世界观背景、势力、核心法则设定 |
| `main_plot.md` | init 自动 | `outlines/main_plot.md` | Stage 0 | 主控 | 全书主线脊柱、开局/中继/终局设定 |
| `volume_outline.md` | init 自动（仅 vol_01） | `outlines/vol_XX/outline.md` | Stage 0 / 开新卷 | 主控 | 开新卷时**手工复制改名**，并注意标题中硬编码的 `vol_01` 卷号要改 |
| `character_card.md` | init 自动（仅主角） | `characters/protagonist.md` | Stage 0 起 | 主控 | 后续角色**手工复制改名**（如 `characters/林编辑.md`——按本书角色自定）；人设卡（Want/Fear、性格与说话风格） |
| `beats.md` | 手工复制/参考 | `outlines/vol_XX/beats/ch_XXX.md` | Stage 1 | 主控 | 单章细纲任务书（戏剧目标 + 场景脉络 + 伏笔线索 + 交付契约） |
| `reader_review.md` | 手工参考 | 参考其 JSON 结构落盘为 `state/inbox/ch_XXX.json` | Stage 4 | Reader | 严谨客观事实审计，直接装配标准增量提案 JSON（消除手工搬运税；模板是 .md 承载 JSON，落盘须存为 .json） |

---

## beats front-matter 合法键清单（引擎强制，超键报错 `beats_fm_extra_keys`）

| 键 | 用途 |
|---|---|
| `chapter` / `vol` | 章号 / 卷号（如 `ch_007` / `vol_01`） |
| `form` | 章型（如 剧情推进）；连章同 form 必须给 `form_reason` |
| `form_reason` | 与上一章同 form 的理由声明 |
| `pov` | 视角角色 |
| `words` | 本章自报字数带（如 `2400-3500`）；与上一章带差 <400 会触发 `words_band_crowded` 警告 |
| `style_notes` | 风格旋钮（竖线分隔）；禁止与上一章全同（`style_notes_copy` 警告） |
| `guard_extra` | 章级禁忌词表（竖线/逗号分隔）；被 `evidence file/style` 并入机械计数 |
| `editor_extra` | 传递给 Editor 的附加约束 |
| `tension_curve` | 张力曲线标记 |

---

## 填写与生命周期规范

1. **槽位填充**：模板中的 `{{slot:xxx}}` 为初始化占位符，完成 Stage 0 设定后填实。`python studio.py check` 会自动检查未填槽位（注意：槽位写法须为 `{{slot:名字}}` 无空格，init 才能自动实例化；带空格的写法只会被 check 拦下）。
2. **人物卡与实体分级建立机制**：
   - **主要/核心角色**：在 `characters/<角色名>.md` 建立独立人物卡（明确 Want/Fear、性格特征与说话风格），并在 `state/entities.json` 注册（实体 `card` 字段填卡文件相对路径，`pack --full` 会注入卡全文）；
   - **次要/临时实体（杂兵/临时道具/背景地点）**：无需手工建卡，由 Stage 4 Reader 自动装配进 `state/inbox/ch_XXX.json`，Stage 5 主控审定后执行 `studio.py sync` 即可自动注册进 `state/entities.json`。
3. **动态细纲任务书格式**：单章 beats 文件头部为 YAML Front-matter（合法键见上表），正文包含 `## 核心冲突与场景脉络`、`## 伏笔与线索动作` 以及 `## 交付契约`（引擎按标题关键字提取这三节，勿改节名结构）。
4. **事实审计与增量提案装配**：Stage 4 Reader 通读定稿正文，客观提炼 5 大事实，直接装配写入 `state/inbox/ch_XXX.json`，供 Stage 5 主控一键核准封存。

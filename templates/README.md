# templates/ — 创作模板库

本目录包含 `studio.py init` 初始化新书时自动生成的各类设定、大纲与细纲模板。

---

## 模板与阶段对照

| 模板文件 | 实例化目标路径 | 填写阶段 | 负责角色 | 说明 |
|---|---|---|---|---|
| `project_bible.md` | `bible/project_bible.md` | Stage 0 | 主控 | 世界观背景、势力、核心法则设定 |
| `main_plot.md` | `outlines/main_plot.md` | Stage 0 | 主控 | 全书主线脊柱、开局/中继/终局设定 |
| `volume_outline.md` | `outlines/vol_XX/outline.md` | Stage 0 / 开新卷 | 主控 | 分卷大纲规划与核心高潮走向 |
| `character_card.md` | `characters/<角色名>.md` | Stage 0 起 | 主控 | 核心人物人设卡（Want/Fear、性格特征与说话风格） |
| `beats.md` | `outlines/vol_XX/beats/ch_XXX.md` | Stage 1 | 主控 | 单章细纲任务书（戏剧目标 + 场景脉络 + 伏笔线索 + 交付契约） |
| `reader_review.md` | `state/inbox/ch_XXX.json` | Stage 4 | Reader | 严谨客观事实审计，直接装配标准增量提案 JSON（消除手工搬运税） |

---

## 填写与生命周期规范

1. **槽位填充**：模板中的 `{{slot:xxx}}` 为初始化占位符，完成 Stage 0 设定后填实。`python studio.py check` 会自动检查未填槽位。
2. **人物卡与实体分级建立机制**：
   - **主要/核心角色**：在 `characters/<角色名>.md` 建立独立人物卡（明确 Want/Fear、性格特征与说话风格），并在 `state/entities.json` 注册；
   - **次要/临时实体（杂兵/临时道具/背景地点）**：无需手工建卡，由 Stage 4 Reader 自动装配进 `state/inbox/ch_XXX.json`，Stage 5 主控审定后执行 `studio.py sync` 即可自动注册进 `state/entities.json`。
3. **动态细纲任务书格式**：单章 beats 文件头部为 YAML Front-matter，正文包含 `## 核心冲突与场景脉络`、`## 伏笔与线索动作` 以及 `## 交付契约`。
4. **事实审计与增量提案装配**：Stage 4 Reader 通读定稿正文，客观提炼 5 大事实，直接装配写入 `state/inbox/ch_XXX.json`，供 Stage 5 主控一键核准封存。

# templates/ — 创作模板库

本目录包含 `studio.py init` 初始化新书时自动生成的各类设定、大纲与细纲模板。

---

## 模板与阶段对照

| 模板文件 | 实例化目标路径 | 填写阶段 | 负责角色 | 说明 |
|---|---|---|---|---|
| `project_bible.md` | `bible/project_bible.md` | Stage 0 | 主控 | 世界观背景、势力、核心法则及「偏离清单」 |
| `main_plot.md` | `outlines/main_plot.md` | Stage 0 | 主控 | 全书主线脊柱、开局/中继/终局设定 |
| `volume_outline.md` | `outlines/vol_XX/outline.md` | Stage 0 / 开新卷 | 主控 | 单卷通用戏剧节拍矩阵（四阶段）与承诺兑现 |
| `character_card.md` | `characters/<角色名>.md` | Stage 0 起 | 主控 | 核心人物设定卡（Want/Fear、Voice Profile 声纹口吻与语言禁忌） |
| `beats.md` | `outlines/vol_XX/beats/ch_XXX.md` | Stage 1 | 主控 | 单章细纲与任务书（动态场景切片 + 多元张力波形 + 交付契约） |
| `reader_review.md` | `log/review/ch_XXX.md` | Stage 3.5 | Reader | 商业网文 5 维雷达打分、毒点与水文风控、验收判定与 300~600 字事实简报 |

---

## 填写与生命周期规范

1. **槽位填充**：模板中的 `{{slot:xxx}}` 为初始化占位符，完成 Stage 0 设定后填实。`python studio.py check` 会自动检查未填槽位。
2. **人物卡与实体分级建立机制**：
   - **主要/核心角色**：在 `characters/<角色名>.md` 建立独立人物卡（填实 Want/Fear、Voice Profile 声纹锚定与语言禁忌），并在 `state/entities.json` 注册；
   - **次要/临时实体（杂兵/临时道具/背景地点）**：无需手工建卡，由 Stage 3.5 Reader 提炼至事实简报，Stage 4 主控在 `state/inbox/ch_XXX.json` 声明后，执行 `studio.py sync` 即可自动注册进 `state/entities.json`。
3. **动态细纲任务书格式**：单章 beats 文件头部为 YAML Front-matter（指定当章 Form、POV、字数区间与张力波形类型），正文包含 `## 拍点与场景切片`（2~4 个动态切片）、`## 伏笔与线动作` 以及 `## 交付契约`（目标情绪、禁忌与验收标准）。
4. **读者评审与事实审计**：Stage 3.5 Reader 输出商业网文 5 维雷达评分、契约验收逐条带证据判定（`1. ✓ [证据]...`）与 300~600 字结构化事实简报，可持久化留存于 `log/review/ch_XXX.md`。

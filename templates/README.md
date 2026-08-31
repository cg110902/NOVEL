# templates/ — 创作模板库

本目录包含 `studio.py init` 初始化新书时自动生成的各类模板。

---

## 模板与阶段对照

| 模板文件 | 实例化目标路径 | 填写阶段 | 负责角色 | 说明 |
|---|---|---|---|---|
| `project_bible.md` | `bible/project_bible.md` | Stage 0 | 主控 | 世界观背景、势力、核心法则及「偏离清单」 |
| `main_plot.md` | `outlines/main_plot.md` | Stage 0 | 主控 | 全书主线脊柱、开局/中继/终局设定 |
| `volume_outline.md` | `outlines/vol_XX/outline.md` | Stage 0/开新卷 | 主控 | 分卷剧情战役发展 |
| `character_card.md` | `characters/<角色名>.md` | Stage 0 起 | 主控 | 人物设定卡（动机、恐惧、关系） |
| `beats.md` | `outlines/vol_XX/beats/ch_XXX.md` | Stage 1 | 主控 | 单章细纲与任务书（Front-matter + 拍点 + 约束） |

---

## 填写规范

1. **槽位填充**：模板中的 `{{slot:xxx}}` 为初始化占位符，完成 Stage 0 设定后填实。`python studio.py check` 会自动检查未填槽位。
2. **细纲任务书格式**：单章 beats 文件头部为 YAML Front-matter，正文包含 `## 拍点`、`## 线动作` 以及任务书四节（`## 目标`、`## 必须保留`、`## 本章禁忌`、`## 验收`）。


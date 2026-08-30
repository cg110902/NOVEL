# templates/ — 模板地图（填什么不在此规定）

每个文件由 `studio.py init` 实例化到书工作区；文件内的 `<!-- 引导 -->` 注释是「该装什么」的
**唯一**内容规格（填完可删）。本 README 只回答另外三件事：哪个文件、哪个 Stage、谁填、
落在哪、哪部分是机器解析的。内容规格不复述——复述会产生第二份真相。

## 实例化对照

| 模板 | 实例化到（书工作区内） | 填写时机 | 谁填 | 机器解析部分 |
|---|---|---|---|---|
| `project_bible.md` | `bible/project_bible.md` | Stage 0 | 主控 | 无（自由文本；「本书偏离清单」节被 pack 硬提醒逐条注入） |
| `main_plot.md` | `outlines/main_plot.md` | Stage 0 | 主控 | 无 |
| `volume_outline.md` | `outlines/vol_XX/outline.md` | Stage 0（每卷开卷时；Stage 1 输入合同要它） | 主控 | 无 |
| `character_card.md` | `characters/<角色>.md` | Stage 0 起随时 | 主控 | 无（机器字段在 `state/entities.json`，卡上只写「像什么」） |
| `beats.md` | `outlines/vol_XX/beats/ch_NNN.md` | Stage 1（每章） | 主控 | **front-matter 六键——全仓库唯一被引擎解析的散文区**（合法键见 `novel_craft.md#front-matter 键`） |

## 不变量（四条）

1. front-matter 之外的正文与一切交付文档**零格式义务**——引擎不读，主控不查格式。
2. beats 尾部任务书四节（目标/必须保留/本章禁忌/验收）的节标题名是合同（`check` 按
   `^##\s*<节名>` 找节）；节内自由。不要额外写空的 `## 任务书` 标题。
3. 未填的 `{{slot:}}` 会被 `check` 拦（unfilled_slot）——init 之后先填资产，再进 Stage 1。
4. 模板改动只改 `templates/`；已 init 的书不回溯改（书工作区的副本是历史事实）。

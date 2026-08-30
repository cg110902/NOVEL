# Novel Studio

> 五阶段流水线：Stage 0 初始化 → 1 细纲+任务书（主控）→ 2 起草（一次性子代理）→ 3 重铸&精修（一次性子代理）→ 4 同步（主控）。LLM 干一切灵活的活，Python 只做白名单死板事。

> 创作规则入口指引： `AGENTS.md`。

## 快速上手（宿主 Agent / 人类通用）

```bash
python studio.py init -w workspace/我的书 -t 书名 -g 题材 -p 主角名   # Stage 0
python studio.py status                                             # 开局必读：进度+下一步
python studio.py pack ch_001          # 装配子代理上下文（P0/P1/P2 三层）
python studio.py evidence words       # 机械证据：字数/提及/线状态/查重/风格指纹（纯 JSON）
python studio.py check                # 事实级体检：errors 阻断，warnings 只报数
python studio.py sync ch_001          # 提案合并 → 状态体检 → 快照（Stage 4）
python studio.py proposal new ch_002 --write   # 生成并写入下一章提案骨架（state/inbox/ch_002.json）
python studio.py snapshot rollback ch_001_done --clean-drafts      # 回滚
python studio.py export --txt         # 全书编译


```

## 文档地图

| 层 | 文件 | 一句话 |
|---|---|---|
| 文档层 | `AGENTS.md` | 宪法：禁令/不变量/开局地图  |
| | `agents/rules/novel_workflow.md` | 流水线剧本（Stage 0–4 SOP） |
| | `agents/rules/novel_craft.md` | 文学默认值（可被「本书偏离清单」覆盖） |
| | `agents/skills/*/SKILL.md` | 5 张岗位合同（director/beats-builder/drafter/guard/syncer） |
| | `agents/genre_guide.md` | 8 题材选择题素材（非公式） |
| 引擎层 | `studio.py` + `engine/` | 10 命令薄壳；纯 stdlib；模块依赖 cli → 各领域 → common |
| 数据层 | `workspace/<书名>/` | 圣经/大纲/稿件自由文本；`state/` 6 JSON = 机器真值（提案制写入） |
 
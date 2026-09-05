"""CLI 薄壳：24 命令参数解析与总调度；命令实现分置于 engine/commands/* 三模块。

status / init / cockpit / pack / evidence / check / checkpoint / state / config / sync / snapshot / export /
dashboard / proposal / review / beats / critic / graph / errcodes / help / ask / pov / calendar / ledger。
退出码：0=ok / 1=阻断（含 check errors、sync 失败）/ 2=用法错。
"""
from __future__ import annotations

import argparse
import json

from . import __version__, common
from .commands._shared import _add_common_opts
from .commands.book_setup import cmd_config, cmd_cockpit, cmd_errcodes, cmd_init, cmd_status
from .commands.chapter_flow import (cmd_ask, cmd_beats, cmd_calendar, cmd_check, cmd_critic,
                                    cmd_dashboard, cmd_evidence, cmd_export, cmd_graph, cmd_pack,
                                    cmd_pov, cmd_review)
from .commands.state_sync import (cmd_checkpoint, cmd_ledger, cmd_proposal, cmd_snapshot,
                                  cmd_state, cmd_sync)


# ---------------------------------------------------------------------------
# help（命令目录与实战配方：与 parser 强内聚，留在调度壳）
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# help
# ---------------------------------------------------------------------------
COMMAND_HELP = {
    "status": "进度总览 + 逐章流水线 + 下一步指向",
    "init": "创建/清理书工作区（脚手架+状态播种+模板槽位实例化）",
    "cockpit": "主控态势驾驶舱：工作流导航 + 戏剧动力学 + 伏笔雷达 + 自愈处方 + 催更雷达",
    "pack": "单章上下文三层装配（P0 热 / P1 别名触发 / P2 冷索引）",
    "ask": "全书事实检索机（只读取证：别名展开→六表+final 原句双域，带章节出处；写细纲前先问书）",
    "pov": "角色视角包（档案/持有/关系/出场足迹/他知道与不知道的/未了线——由账本推导，advisory）",
    "calendar": "未来 N 章排产日历（到期线/危机时钟/卷阶段里程碑投影；Stage 1 排产前置参考）",
    "evidence": "机械证据：all|mentions|gaps|names|dup|style|words|file|candidates|prev（纯 JSON，零裁决）",
    "check": "结构/schema/算术体检（errors 只允许事实级；有 errors 退出码 1；新书 Stage 0 待办不阻断）",
    "checkpoint": "宏观航向校准点（每5章复盘分卷四分位里程碑与主线偏航）",
    "state": "状态速查与手术刀纠偏：state show ｜ get <表.字段> ｜ set <表.字段> <值>（如 state get current.time；防真值幻觉）",
    "config": "书级参数手术刀：list|guide|suggest|get|set[--merge]|unset（主控供参通道，project.json；含 words_target/lines_cap 等项目级键）",
    "sync": "提案合并 → 状态体检 → 快照（Stage 5 闭环，可 --dry-run）",
    "ledger": "账本手术刀：recompute（余额与 balance_after 按流水全量重算修复）",
    "snapshot": "快照 list / create NAME / rollback NAME [--clean-drafts]",
    "export": "全书编译：--txt 拼接正文，--views 渲染状态视图",
    "proposal": "提案：new 骨架 ｜ auto 自动装配 ｜ check 结构预检+三方事实对照 ｜ verify 算法版Stage4.5机械对照",
    "dashboard": "生成交互式全景看板 HTML（人物关系网/伏笔看板/情绪心电图）",
    "review": "校对注记：new <章节>（骨架预填验收条目+机器数据，--write 写 log/review/）",
    "beats": "细纲脚手架：new [章节]（Stage 1 智能生成带字数预算与情绪蓄水泵的 beats 任务书）",
    "critic": "老白读者催更便签：查看 Stage 4B 便签或落盘 SKELETON 预填骨架（骨架不替代子代理评审）",
    "graph": "实体拓扑沙盘与叙事中介寻路（NetworkX 强力赋能：path/neighbors/isolated/centrality）",
    "errcodes": "错误码注册表速查：全部体检码的 severity/解释/修复建议（--json 供 Agent）",
    "help": "本命令目录与实战配方（--json 供 Agent 解析速查）",
}

STAGE_MAP = {
    "Stage 0 (设定构想)": {
        "role": "Director",
        "description": "确立世界观法则、人物卡、分卷大纲与词表供参",
        "commands": ["init", "config"],
    },
    "Stage 1 (细纲装配)": {
        "role": "Director",
        "description": "吸收上章 Critic 建议、装配戏剧冲突、细纲任务书与拓扑破局",
        "commands": ["beats", "graph"],
    },
    "Stage 2-3 (起草与重塑)": {
        "role": "Drafter & Editor",
        "description": "初稿剧情爆发起草，顺畅读感文学重塑，一次成型直接落盘",
        "commands": ["pack"],
    },
    "Stage 4 (双轨质检)": {
        "role": "Reader & Critic",
        "description": "事实审计提案生成（轨A）与老白读者毒舌评测（轨B）原生并发",
        "commands": ["evidence", "critic", "proposal"],
    },
    "Stage 5 (同步与封存)": {
        "role": "Director",
        "description": "状态原子合并、全书机械体检、快照归档与全景看板",
        "commands": ["sync", "check", "checkpoint", "snapshot", "dashboard", "export", "state"],
    },
}

RECIPES = [
    {
        "name": "推进新章标准流水线",
        "stage_flow": "Stage 1 -> Stage 5",
        "steps": [
            "python studio.py beats new ch_XXX --write",
            "python studio.py pack ch_XXX",
            "# (Stage 2 Drafter 起草 raw/ch_XXX_v1.md)",
            "# (Stage 3 Editor 精修 final/ch_XXX.md)",
            "# (Stage 4 Reader 提案 state/inbox/ch_XXX.json 并行 Critic 评测)",
            "python studio.py sync ch_XXX",
        ],
    },
    {
        "name": "写作前取证（问书三件套，严禁凭记忆脑补）",
        "stage_flow": "Stage 1",
        "steps": [
            "python studio.py ask <关键词/实体名/线索ID>   # 全书事实检索：六表+正文原句，带章节出处",
            "python studio.py pov <角色名>                # 角色视角包：他知道什么/不知道什么/未了线",
            "python studio.py calendar [N]                # 未来 N 章排产日历：到期线/时钟/里程碑",
        ],
    },
    {
        "name": "剧情写偏/状态污染安全回滚",
        "stage_flow": "Any -> Rollback",
        "steps": [
            "python studio.py snapshot list",
            "python studio.py snapshot rollback <SNAPSHOT_NAME> --clean-drafts",
        ],
    },
    {
        "name": "寻找两角色间破局中介与利益链路",
        "stage_flow": "Stage 1",
        "steps": [
            "python studio.py graph path <起点角色> <目标角色>",
            "python studio.py graph centrality",
        ],
    },
    {
        "name": "全书事实一致性与叙事健康体检",
        "stage_flow": "Stage 5 / Regular",
        "steps": [
            "python studio.py check",
            "python studio.py checkpoint",
            "python studio.py ledger recompute   # 账目存疑时按流水全量重算修复",
        ],
    },
]


def cmd_help(args) -> int:
    parser = _build_parser()
    subs = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    names = list(subs.choices)
    if args.json:
        payload = {
            "version": __version__,
            "exit_codes": {"0": "ok", "1": "blocked", "2": "usage"},
            "stages": STAGE_MAP,
            "recipes": RECIPES,
            "commands": [{"name": n, "help": COMMAND_HELP.get(n, "")} for n in names],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print("======================================================================")
    print(f" 🚀 Novel Studio 确定性引擎 v{__version__}（创作规则见 AGENTS.md）")
    print("======================================================================")
    print("【工序阶段与命令分布】")
    for stage_name, stage_info in STAGE_MAP.items():
        cmds_str = "、".join(stage_info["commands"])
        print(f"  • {stage_name} [{stage_info['role']}]: {stage_info['description']}")
        print(f"    命令: {cmds_str}")
    print("\n【常用实战配方 (Recipes)】")
    for r in RECIPES:
        print(f"  ⚡ {r['name']} ({r['stage_flow']}):")
        for s in r["steps"]:
            print(f"     {s}")
    print("\n【全部可用命令速查】")
    for n in names:
        print(f"  {n:<11} {COMMAND_HELP.get(n, '')}")
    print("\n退出码：0=ok ｜ 1=阻断 ｜ 2=用法错。Agent 首选各命令的 --json 参数。")
    return 0


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="studio", description="Novel Studio 确定性引擎（薄壳）")
    p.add_argument("--version", action="version", version=f"novel-studio {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    _build_subparsers(sub)
    return p


def _build_subparsers(sub: argparse._SubParsersAction) -> None:
    q = sub.add_parser("status", help="进度总览 + 逐章流水线 + 下一步指向")
    _add_common_opts(q)
    q.set_defaults(func=cmd_status)

    q = sub.add_parser("cockpit", help="主控态势驾驶舱：工作流导航 + 戏剧动力学 + 自愈处方 + 催更雷达")
    _add_common_opts(q)
    q.add_argument("chapter", nargs="?", help="目标章节（如 2 或 ch_002，缺省自动推断活跃章）")
    q.set_defaults(func=cmd_cockpit)

    q = sub.add_parser("init", help="创建/清理书工作区（脚手架+状态播种+模板槽位实例化）")
    _add_common_opts(q, json_flag=False)
    q.add_argument("-t", "--title", help="书名")
    q.add_argument("-g", "--genre", help="题材（如 仙侠/悬疑/科幻）")
    q.add_argument("-p", "--protagonist", help="主角名")
    q.add_argument("--clean", action="store_true",
                   help="清稿重来（清 raw 草稿与待办提案；保留 final 定稿/圣经/细纲/审计与状态；"
                        "--deep 才连 final 定稿一并清理）")
    q.add_argument("--deep", action="store_true",
                   help="配合 --clean 使用：连 final 定稿一并删除（状态六表仍保留，事实源将分裂，慎用）")
    q.add_argument("--force", action="store_true",
                   help="整本重开（仅限已登记书目录；原书整体移入 workspace/.trash/ 回收区备份，"
                        "不直接删除；确认无需后可手动清理回收区）")
    q.set_defaults(func=cmd_init)

    q = sub.add_parser("pack", help="单章上下文打包（P0 热/P1 触发/P2 冷索引）")
    _add_common_opts(q)
    q.add_argument("chapter", nargs="?", help="目标章节（如 7 或 ch_007）")
    q.add_argument("--lean", action="store_true", help="只给 P0")
    q.add_argument("--full", action="store_true", help="P1 命中实体附卡全文")
    q.add_argument("--open", dest="open_path", help="取工作区内任一文件原文（相对路径）")
    q.set_defaults(func=cmd_pack)

    q = sub.add_parser("ask", help="全书事实检索机（只读取证：六表+final 原句双域，带章节出处）")
    _add_common_opts(q)
    q.add_argument("query", help="关键词/实体名/线索ID（如：灵石 / 苏九娘 / GUN-001）")
    q.set_defaults(func=cmd_ask)

    q = sub.add_parser("pov", help="角色视角包（档案/持有/关系/足迹/他知道与不知道的/未了线）")
    _add_common_opts(q)
    q.add_argument("name", help="角色/实体名称（支持别名）")
    q.set_defaults(func=cmd_pov)

    q = sub.add_parser("calendar", help="未来 N 章排产日历（到期线/危机时钟/阶段里程碑投影）")
    _add_common_opts(q)
    q.add_argument("span", nargs="?", type=int, default=5, help="投影章数（默认 5，上限 12）")
    q.set_defaults(func=cmd_calendar)

    q = sub.add_parser("evidence", help="机械证据：all|mentions|gaps|names|dup|style|words|file|candidates|prev")
    _add_common_opts(q)
    q.add_argument("kind", choices=["all", "mentions", "gaps", "names", "dup", "style", "words", "file",
                                    "candidates", "prev"])
    q.set_defaults(func=cmd_evidence)
    q.add_argument("args", nargs="*", help="kind 参数（名字/章节等）")

    q = sub.add_parser("check", help="结构/schema/算术体检（errors 只允许事实级）")
    _add_common_opts(q)
    q.set_defaults(func=cmd_check)

    q = sub.add_parser("checkpoint", help="宏观航向校准点（每5章复盘分卷四分位里程碑与主线偏航）")
    _add_common_opts(q)
    q.add_argument("chapter", nargs="?", help="复盘目标章节（默认最新定稿/细纲章）")
    q.set_defaults(func=cmd_checkpoint)

    q = sub.add_parser("state", help="状态速查与手术刀纠偏：show ｜ get <表.字段> ｜ set <表.字段> <值>")
    _add_common_opts(q)
    st_sub = q.add_subparsers(dest="state_action")
    r = st_sub.add_parser("show", help="速览当前现场状态 (current.json)")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_state)
    r = st_sub.add_parser("get", help="查看指定字段值（例如: current.injury 或 entities.林舟.realm）")
    r.add_argument("target", help="字段路径")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_state)
    r = st_sub.add_parser("set", help="直接设置/纠偏指定字段（例如: current.injury \"轻伤已愈\"）")
    r.add_argument("target", help="字段路径")
    r.add_argument("value", help="新值（支持普通文本或 JSON 结构）")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_state)
    q.set_defaults(func=cmd_state)

    q = sub.add_parser("config", help="书级参数手术刀：list(默认)|guide|suggest|get|set|unset（主控供参通道，含 words_target/lines_cap）")
    _add_common_opts(q)
    cf_sub = q.add_subparsers(dest="config_action")
    for _name, _hlp, _extra in (
            ("list", "列出全部参数键的配置状态与当前值", ()),
            ("guide", "引擎可接受参数的型号单（形状+示例，主控照此供参）", ()),
            ("suggest", "供参候选工作单（机械计数高频短别名/泛词，主控裁决采纳）", ()),
            ("get", "查看指定参数键（-w 书目录）", ("key",)),
            ("set", "设置参数（值为 JSON 字面量；[]/{}=明确关闭；--merge 并入现有值）", ("key", "value")),
            ("unset", "移除参数（回到未配置态；gap 键将恢复缺口提示）", ("key",))):
        r = cf_sub.add_parser(_name, help=_hlp)
        for _pos in _extra:
            r.add_argument(_pos)
        if _name == "set":
            r.add_argument("--merge", action="store_true",
                           help="并入现有值（数组并集去重 / 分档并集），而非整体替换")
        r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
        r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
        r.set_defaults(func=cmd_config)
    q.set_defaults(func=cmd_config)

    q = sub.add_parser("sync", help="提案合并 → 状态体检 → 快照（Stage 5 闭环）")
    _add_common_opts(q)
    q.add_argument("chapter", help="目标章节（如 7 或 ch_007）")
    q.add_argument("--dry-run", action="store_true", help="只校验预演不写入")
    q.set_defaults(func=cmd_sync)

    q = sub.add_parser("snapshot", help="快照：list（默认）| create NAME | rollback NAME")
    _add_common_opts(q)
    snap = q.add_subparsers(dest="snap_action")
    r = snap.add_parser("list", help="快照列表（默认动作）")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_snapshot)
    r = snap.add_parser("create", help="创建具名快照")
    r.add_argument("name")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_snapshot)
    r = snap.add_parser("rollback", help="回滚到匹配名称的最新快照")
    r.add_argument("name")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--clean-drafts", action="store_true", help="一并清理该快照之后的孤立章节/细纲")
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_snapshot)
    q.set_defaults(func=cmd_snapshot)

    q = sub.add_parser("ledger", help="账本手术刀：recompute（余额按流水全量重算修复）")
    _add_common_opts(q)
    lg = q.add_subparsers(dest="ledger_action")
    r = lg.add_parser("recompute", help="余额与 balance_after 按流水全量重算并修复")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_ledger)
    q.set_defaults(func=cmd_ledger)

    q = sub.add_parser("export", help="全书编译：--txt 拼接正文，--views 渲染状态视图")
    _add_common_opts(q)
    q.add_argument("--txt", action="store_true", help="导出 export/<书名>.txt")
    q.add_argument("--views", action="store_true", help="导出 export/views/state_view.md")
    q.set_defaults(func=cmd_export)

    q = sub.add_parser("dashboard", help="全景可视化看板：导出 HTML 交互式人物图谱与伏笔看板")
    _add_common_opts(q)
    q.set_defaults(func=cmd_dashboard)

    q = sub.add_parser("proposal", help="提案：new 骨架 ｜ auto 自动装配 ｜ check 结构预检+三方对照")
    _add_common_opts(q)
    pp = q.add_subparsers(dest="pp_action")
    r = pp.add_parser("new", help="生成最小合法骨架（schema/chapter/operation_id 预填）")
    r.add_argument("chapter")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.add_argument("--write", action="store_true", help="直接写入 state/inbox/ch_XXX.json（默认只打印）")
    r.set_defaults(func=cmd_proposal)
    r = pp.add_parser("auto", help="基于 beats 与 final 自动装配高精准度提案草案")
    r.add_argument("chapter")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.add_argument("--write", action="store_true", help="直接写入 state/inbox/ch_XXX.json（默认只打印）")
    r.add_argument("--force", action="store_true", help="已有在途提案时强制覆盖（谨慎）")
    r.set_defaults(func=cmd_proposal)
    r = pp.add_parser("check", help="在途提案结构预检 + 三方事实对照（不落盘）")
    r.add_argument("chapter")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_proposal)
    r = pp.add_parser("verify", help="Stage 5 机械对照：0 token 机械对照电池（候选清单，不阻断）")
    r.add_argument("chapter")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_proposal)
    q.set_defaults(func=cmd_proposal)

    q = sub.add_parser("review", help="校对注记骨架：new <章节>（预填验收条目+机器数据）")
    _add_common_opts(q)
    rv = q.add_subparsers(dest="rev_action")
    r = rv.add_parser("new", help="生成注记骨架（默认打印；--write 写 log/review/ch_XXX.md）")
    r.add_argument("chapter")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.add_argument("--write", action="store_true", help="写入 log/review/ch_XXX.md（已存在则拒绝）")
    r.set_defaults(func=cmd_review)
    q.set_defaults(func=cmd_review)

    q = sub.add_parser("beats", help="细纲脚手架：new [章节]（Stage 1 智能生成带字数预算的 beats 任务书）")
    _add_common_opts(q)
    bt = q.add_subparsers(dest="beats_action")
    r = bt.add_parser("new", help="生成当章细纲任务书脚手架（自动注入规划/上章现场/到期伏笔）")
    r.add_argument("chapter", nargs="?", default=None, help="目标章节（缺省自动选下一章）")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.add_argument("--write", action="store_true", help="直接写入 outlines/vol_XX/beats/ch_XXX.md")
    r.add_argument("--force", action="store_true", help="细纲已存在时强制覆盖")
    r.set_defaults(func=cmd_beats)
    q.set_defaults(func=cmd_beats)

    q = sub.add_parser("critic", help="老白读者毒舌评测：查看或生成毒点/爽点/留存分析报告（Stage 4 并行质检）")
    _add_common_opts(q)
    q.add_argument("chapter", nargs="?", default=None, help="目标章节（缺省自动选最新定稿）")
    q.add_argument("--write", action="store_true", help="写入 log/critic/ch_XXX.md 评测骨架")
    q.set_defaults(func=cmd_critic)

    q = sub.add_parser("graph", help="实体拓扑沙盘与叙事中介寻路（NetworkX 驱动）")
    _add_common_opts(q)
    gp = q.add_subparsers(dest="graph_action")
    r = gp.add_parser("summary", help="全图拓扑总览（节点数、连通分支、资产统计）")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_graph)

    r = gp.add_parser("path", help="两实体间最短剧情/社交破局链路寻路")
    r.add_argument("source", help="起点实体名称")
    r.add_argument("target", help="终点实体名称")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_graph)

    r = gp.add_parser("neighbors", help="查看指定实体的 1-Hop/2-Hop 关联网络")
    r.add_argument("name", help="实体名称")
    r.add_argument("--depth", type=int, default=1, choices=[1, 2], help="关联跳数")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_graph)

    r = gp.add_parser("isolated", help="排查全书孤立/边缘资产（防伏笔与人物烂尾）")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_graph)

    r = gp.add_parser("centrality", help="计算全书角色与道具的剧情中介枢纽排名")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_graph)
    q.set_defaults(func=cmd_graph)

    q = sub.add_parser("help", help="命令目录")
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_help)

    q = sub.add_parser("errcodes", help="错误码注册表速查（severity/解释/修复建议）")
    q.add_argument("--json", action="store_true", help="结构化 JSON 输出（Agent 首选）")
    q.set_defaults(func=cmd_errcodes)


def main(argv: list[str] | None = None) -> int:
    common.reconfigure_utf8()
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        print("\n⏸ 已中断（状态文件有原子写保护，重跑 status 看现场）")
        return 130
    except (ValueError, TimeoutError) as exc:
        print(f"❌ {exc}")
        return 1
    except OSError as exc:
        print(f"❌ 文件系统错误: {exc}")
        print("   💡 Windows 下常见于文件被占用（杀毒/索引/同步盘）。稍候重试，或关闭占用方后重跑。")
        return 1

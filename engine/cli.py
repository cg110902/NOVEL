"""CLI 薄壳：30 个命令名（29 个处理函数，check 与 doctor 共用 cmd_check）参数解析与总调度；
命令实现分置于 engine/commands/* 五模块。命令目录的唯一自查入口是 `python studio.py help --json`。

status / init / cockpit / pack / evidence / index / check / doctor / checkpoint / state / config /
sync / snapshot / export / proposal / review / beats / critic / graph / errcodes / help / ask /
pov / calendar / ledger / audit / recall / simulate / milestone / lore。
退出码：0=ok / 1=阻断（含 check errors、sync 失败）/ 2=用法错 /
3=运行环境缺依赖（studio.py 在 import 期兜住并给出安装命令）。
"""
from __future__ import annotations

import argparse
import json
import sys

from . import __version__, common, pack
from .commands._shared import _add_common_opts
from .commands.book_setup import (cmd_config, cmd_cockpit, cmd_errcodes, cmd_init, cmd_status,
                                  cmd_lore)
from .commands.chapter_flow import (cmd_ask, cmd_audit, cmd_beats, cmd_calendar, cmd_check, cmd_critic,
                                    cmd_evidence, cmd_export, cmd_graph, cmd_index, cmd_pack,
                                    cmd_pov, cmd_review)
from .commands.recall import cmd_recall
from .commands.simulate import cmd_simulate
from .commands.state_sync import (cmd_checkpoint, cmd_ledger, cmd_milestone, cmd_proposal, cmd_snapshot,
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
    "ask": "全书事实检索机（只读取证：别名展开→八表+final 原句双域，带章节出处；写细纲前先问书）",
    "pov": "角色视角包（档案/持有/关系/出场足迹/他知道与不知道的/未了线——由账本推导，advisory）",
    "calendar": "未来 N 章排产日历（到期线/危机时钟/卷阶段里程碑投影；Stage 1 排产前置参考）",
    "evidence": "机械证据：all|mentions|gaps|names|dup|style|words|file|candidates|prev|index（纯 JSON，零裁决）",
    "index": "SQLite3 双平面投影索引：构建/重建 FTS5 BM25 全文检索与关系表缓存",
    "check": "结构/schema/算术体检（errors 只允许事实级；有 errors 退出码 1；新书 Stage 0 待办不阻断；--trend 看一致性分数曲线）",
    "doctor": "check 的同义别名（同一处理函数 cmd_check，输出逐字节相同）；习惯叫 doctor 的人用它",
    "checkpoint": "宏观航向校准点（每5章复盘分卷四分位里程碑与主线偏航）",
    "milestone": "主线里程碑管理：list ｜ add（Stage 0 播种主线里程碑与预期达成章节）",
    "state": "状态速查与手术刀纠偏：state show ｜ get <表.字段> ｜ set <表.字段> <值>（如 state get current.time；防真值幻觉）",
    "config": "书级参数手术刀：list|guide|suggest|get|set[--merge]|unset（主控供参通道，project.json；含 words_target/lines_cap 等项目级键）",
    "sync": "提案合并 → 状态体检 → 快照（Stage 5 闭环，可 --dry-run）",
    "ledger": "账本手术刀：recompute（余额与 balance_after 按流水全量重算修复）",
    "snapshot": "快照 list / create NAME / rollback NAME [--clean-drafts]",
    "export": "全书编译：--txt 拼接正文，--views 渲染状态视图",
    "proposal": "提案：new 骨架 ｜ auto 自动装配 ｜ check 结构预检+三方事实对照 ｜ verify 算法版Stage4.5机械对照",
    "review": "校对注记：new <章节>（骨架预填验收条目+机器数据，--write 写 log/review/）",
    "beats": "细纲脚手架：new [章节]（Stage 1 智能生成带字数预算与情绪蓄水泵的 beats 任务书）",
    "critic": "老白读者催更便签：查看 Stage 4B 便签或落盘 SKELETON 预填骨架（骨架不替代子代理评审）",
    "audit": "确定性矛盾排查探针（8大机械探针：在场/充能/金额/KNO/不可逆/认知差/别名漂移/称谓对账；0 Token 候选清单）",
    "recall": "知乎残酷四问 0 Token 机械自证（主要人物知道什么/哪三条不能改/伏笔未兑现/下章红线）",
    "simulate": "剧情推演沙盒与走向假说（impact 因果链测算 ｜ branch 多分支走向参谋件）",
    "graph": "实体拓扑沙盘与叙事中介寻路（NetworkX 强力赋能：path/neighbors/isolated/centrality）",
    "errcodes": "错误码注册表速查：全部体检码的 level/解释/修复建议（--json 供 Agent）",
    "lore": "底层词典与实体知识库速查对账：list（ID总览）｜ entity（实体属性）｜ compare（位阶互称）｜ scale/rules ｜ address",
    "help": "本命令目录与实战配方（--json 供 Agent 解析速查）",
}

STAGE_MAP = {
    "Stage 0 (设定构想)": {
        "role": "Architect 0A/B",
        "description": "确立世界观法则、人物卡、分卷大纲与词表供参等等",
        "commands": ["init", "config", "milestone", "lore"],
    },
    "Stage 1 (细纲装配)": {
        "role": "Director",
        "description": "吸收上章 Critic 建议、装配戏剧冲突、细纲任务书与拓扑破局",
        "commands": ["beats", "lore", "graph", "recall", "simulate"],
    },
    "Stage 2-3 (起草与重塑)": {
        "role": "Drafter & Editor",
        "description": "初稿剧情爆发起草，顺畅读感文学重塑，一次成型直接落盘",
        "commands": ["pack"],
    },
    "Stage 4 (多轨质检)": {
        "role": "Reader & Critic & Auditor",
        "description": "事实审计提案生成（轨A）、老白读者催更评测（轨B）与一致性仲裁（轨C）",
        "commands": ["evidence", "audit", "critic", "proposal"],
    },
    "Stage 5 (同步与封存)": {
        "role": "Director",
        "description": "状态原子合并、全书双核机械体检、快照归档",
        "commands": ["sync", "check", "doctor", "checkpoint", "snapshot", "export", "state"],
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
            "# (Stage 3A Editor 骨肉重塑 raw/ch_XXX_v2.md)",
            "# (Stage 3B Stylist 通俗脱水定稿 final/ch_XXX.md)",
            "# (Stage 4 并发：Reader 提案 state/inbox/ch_XXX.json ｜ Critic 便签 ｜ Auditor 仲裁)",
            "python studio.py audit ch_XXX --write   # 生成带 front-matter 的仲裁报告（Stage 5 闸门必需）",
            "python studio.py sync ch_XXX",
        ],
    },
    {
        "name": "写作前取证（问书三件套，严禁凭记忆脑补）",
        "stage_flow": "Stage 1",
        "steps": [
            "python studio.py ask <关键词/实体名/线索ID>   # 全书事实检索：八表+正文原句，带章节出处",
            "python studio.py pov <角色名>                # 角色视角包：他知道什么/不知道什么/未了线",
            "python studio.py calendar [N]                # 未来 N 章排产日历：到期线/时钟/里程碑",
        ],
    },
    {
        "name": "重大剧情抉择前取证与推演",
        "stage_flow": "Stage 1",
        "steps": [
            "python studio.py recall                        # 0 Token 机械自证知乎残酷四问",
            "python studio.py simulate impact --entity <角色名> --action kill  # 测算角色死亡波及范围",
            "python studio.py simulate branch [ch_XXX]      # 生成多走向假说参谋单",
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
                   help="配合 --clean 使用：连 final 定稿一并删除（状态八表仍保留，事实源将分裂，慎用）")
    q.add_argument("--force", action="store_true",
                   help="整本重开（仅限已登记书目录；原书整体移入 workspace/.trash/ 回收区备份，"
                        "不直接删除；确认无需后可手动清理回收区）")
    q.set_defaults(func=cmd_init)

    q = sub.add_parser("pack", help="单章上下文打包（P0 热/P1 触发/P2 冷索引）")
    _add_common_opts(q)
    q.add_argument("chapter", nargs="?", help="目标章节（如 7 或 ch_007）")
    q.add_argument("--lean", action="store_true", help="只给 P0")
    q.add_argument("--full", action="store_true", help="P1 命中实体附卡全文")
    q.add_argument("--open", dest="open_path",
                   help="取工作区内文件原文（相对路径）；受角色禁读网关约束，默认 --as drafter")
    q.add_argument("--as", dest="as_role", default="drafter",
                   # 单一真源：直接取读权限网关的角色表，杜绝「choices 合法但网关不认」（P0-3）
                   choices=tuple(pack.ROLE_DENY),
                   help="--open 的准读角色（默认 drafter=最严格；主控用 director/evolver 才有全量准读权）")
    q.set_defaults(func=cmd_pack)

    q = sub.add_parser("ask", help="全书事实检索机（只读取证：八表+final 原句双域，带章节出处）")
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

    q = sub.add_parser("evidence", help="机械证据：all|mentions|gaps|names|dup|style|words|file|candidates|prev|index")
    _add_common_opts(q)
    q.add_argument("kind", choices=["all", "mentions", "gaps", "names", "dup", "style", "words", "file",
                                    "candidates", "prev", "index"])
    q.set_defaults(func=cmd_evidence)
    q.add_argument("args", nargs="*", help="kind 参数（名字/章节等）")

    q = sub.add_parser("index", help="SQLite3 只读投影索引构建/重建 (FTS5 + BM25)")
    _add_common_opts(q)
    q.add_argument("--rebuild", "-r", action="store_true", help="强制从头全量清空并重建索引")
    q.set_defaults(func=cmd_index)

    q = sub.add_parser("audit", help="确定性矛盾排查探针（8大机械探针：在场/充能/金额/KNO/不可逆/认知差/别名漂移/称谓对账）")
    _add_common_opts(q)
    q.add_argument("chapter", nargs="?", default="", help="章节标识（如 ch_005，缺省默认最新章）")
    q.add_argument("--write", action="store_true", help="生成并落盘 log/audit/ch_XXX.md 仲裁初稿")
    q.set_defaults(func=cmd_audit)

    q = sub.add_parser("recall", help="知乎残酷四问 0 Token 机械自证（主要人物知道什么/哪三条不能改/伏笔未兑现/下章红线）")
    _add_common_opts(q)
    q.add_argument("chapter", nargs="?", default="", help="锚定章节（如 ch_005，缺省默认最新定稿章）")
    q.set_defaults(func=cmd_recall)

    q = sub.add_parser("simulate", help="剧情推演沙盒与走向假说（impact 因果链测算 ｜ branch 多分支参谋件）")
    _add_common_opts(q)
    sub_sim = q.add_subparsers(dest="simulate_action", required=True)

    p_imp = sub_sim.add_parser("impact", help="因果链波及测算（模拟击杀角色/损毁道具/揭开机密）")
    _add_common_opts(p_imp)
    p_imp.add_argument("--entity", "-e", help="目标实体名称（如 苏九娘）")
    p_imp.add_argument("--line", "-l", help="目标线索编号（如 KNO-001）")
    p_imp.add_argument("--action", "-a", default="mutate", help="模拟动作（如 kill/destroy/reveal）")
    p_imp.set_defaults(func=cmd_simulate)

    p_br = sub_sim.add_parser("branch", help="多分支走向假说参谋单（写至 log/branches/）")
    _add_common_opts(p_br)
    p_br.add_argument("chapter", nargs="?", default="", help="锚定章节（缺省默认最新章）")
    p_br.add_argument("--count", "-c", type=int, default=3, help="候选分支数量（默认 3）")
    p_br.add_argument("--write", action="store_true", help="写入 log/branches/ch_XXX.md")
    p_br.set_defaults(func=cmd_simulate)
    q.set_defaults(func=cmd_simulate)

    q = sub.add_parser("check", help="全息双核健康体检：系统运行时健康 + 叙事健康（errors 只允许事实级；doctor 为其别名）")
    _add_common_opts(q)
    q.add_argument("--trend", action="store_true",
                   help="不跑体检，只看近 N 次的一致性分数曲线（log/scorecard.jsonl）")
    q.set_defaults(func=cmd_check)

    q = sub.add_parser("doctor", help="check 的同义别名（同 cmd_check，输出一致）")
    _add_common_opts(q)
    q.add_argument("--trend", action="store_true", help="同 check --trend")
    q.set_defaults(func=cmd_check)

    q = sub.add_parser("checkpoint", help="宏观航向校准点（每5章复盘分卷四分位里程碑与主线偏航）")
    _add_common_opts(q)
    q.add_argument("chapter", nargs="?", help="复盘目标章节（默认最新定稿/细纲章）")
    q.set_defaults(func=cmd_checkpoint)

    q = sub.add_parser("milestone", help="主线里程碑管理：list（默认）| add（Stage 0 播种主线里程碑与预期达成章节）")
    _add_common_opts(q)
    ms_sub = q.add_subparsers(dest="milestone_action")
    r = ms_sub.add_parser("list", help="里程碑列表（默认动作）")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_milestone)

    r = ms_sub.add_parser("add", help="添加/播种新里程碑（Stage 0 / 1）")
    r.add_argument("--title", "-t", required=True, help="里程碑标题（如「查清灯司黑账」）")
    r.add_argument("--target-ch", "-c", type=int, required=True, help="预期达成章节（正整数）")
    r.add_argument("--id", help="指定里程碑编号（如 MS-001，省略自动生成）")
    r.add_argument("--desc", "-d", default="", help="里程碑详细描述")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_milestone)

    r = ms_sub.add_parser("achieve", help="核销里程碑为已达成（记录实际达成章节）")
    r.add_argument("milestone_id", help="里程碑编号（如 MS-001）")
    r.add_argument("--chapter", "-c", help="实际达成章节（如 ch_010 或 10；省略取当前最新定稿章）")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_milestone)
    q.set_defaults(func=cmd_milestone)

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

    q = sub.add_parser("ledger", help="账本手术刀：recompute（余额按流水全量重算修复）/ pool add（Stage 0 声明资源池）")
    _add_common_opts(q)
    lg = q.add_subparsers(dest="ledger_action")
    r = lg.add_parser("recompute", help="余额与 balance_after 按流水全量重算并修复")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_ledger)
    # Stage 0 原先没有任何 CLI 通道声明资源池（config guide 不含池键、
    # state set 禁登新事实），池只能靠 Stage 5 提案或读源码试出来。
    pa = lg.add_parser("pool", help="资源池管理")
    # pool 子解析器必须自带 -w/--json，否则 `-w <书>` 的值会被 argparse
    # 当成 pool_action 正向参数吃掉（实测 invalid choice: 'workspace/probe'）。
    pa.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    pa.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    pa_sub = pa.add_subparsers(dest="pool_action")
    padd = pa_sub.add_parser("add", help="声明一个新资源池（Stage 0 用；余额由流水重算，不接受 current）")
    padd.add_argument("pool_id", help="池 ID（英文小写下划线，如 lamp_ash）")
    padd.add_argument("--name", required=True, help="显示名（如 灯烬）")
    padd.add_argument("--unit", required=True, help="计量单位（如 盏）")
    padd.add_argument("--initial", type=int, required=True,
                      help="期初值（整数，必填——省略会被当成 0 从而污染账本基准）")
    padd.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    padd.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    pa.set_defaults(func=cmd_ledger)
    padd.set_defaults(func=cmd_ledger)
    q.set_defaults(func=cmd_ledger)

    q = sub.add_parser("export", help="全书编译：--txt 拼接正文，--views 渲染状态视图")
    _add_common_opts(q)
    q.add_argument("--txt", action="store_true", help="导出 export/<书名>.txt")
    q.add_argument("--views", action="store_true", help="导出 export/views/state_view.md")
    q.set_defaults(func=cmd_export)

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
    q.add_argument("-w", "--workspace", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    q.add_argument("--json", action="store_true")
    q.set_defaults(func=cmd_help)

    q = sub.add_parser("errcodes", help="错误码注册表速查（level/解释/修复建议）")
    q.add_argument("-w", "--workspace", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    q.add_argument("--json", action="store_true", help="结构化 JSON 输出（Agent 首选）")
    q.set_defaults(func=cmd_errcodes)

    q = sub.add_parser("lore", help="底层词典与实体知识库速查对账：list ｜ entity ｜ query ｜ compare ｜ address ｜ scale ｜ rules ｜ get")
    _add_common_opts(q)
    lore_sub = q.add_subparsers(dest="lore_action")

    r = lore_sub.add_parser("list", help="查看全部词典模块与实体卡全景清单（默认动作）")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_lore)

    r = lore_sub.add_parser("entity", help="查询单个实体的全息结构化档案与卡片物象")
    r.add_argument("name", help="角色/道具/势力/地标名称")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_lore)

    r = lore_sub.add_parser("query", help="精准字段寻值（如 query 林牧 tier_rank）")
    r.add_argument("name", help="实体名称")
    r.add_argument("field", help="查询属性（如 tier_rank, power_benchmark, address_matrix, charges, holder 等）")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_lore)

    r = lore_sub.add_parser("compare", help="两角色/实体间实力位阶、法定称谓与外交关系侧对侧对校")
    r.add_argument("char_a", help="实体A名称")
    r.add_argument("char_b", help="实体B名称")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_lore)

    r = lore_sub.add_parser("scale", help="提取世界观位阶体系与物理破坏力标尺（来自 02_power_system）")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_lore)

    r = lore_sub.add_parser("rules", help="提取世界观底层不可违背客观公理（来自 01_world_axioms）")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_lore)

    r = lore_sub.add_parser("address", help="速查两角色之间的法定称谓对账矩阵")
    r.add_argument("topic", help="角色A名称")
    r.add_argument("extra", nargs="?", default="", help="角色B名称（可选）")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_lore)

    r = lore_sub.add_parser("get", help="查看指定词典模块或实体卡全文")
    r.add_argument("topic", help="词典主题(axioms/power/factions/economy/mechanics/style/deviations)或角色/实体名")
    r.add_argument("-w", "--workspace", default=argparse.SUPPRESS)
    r.add_argument("--json", action="store_true", default=argparse.SUPPRESS)
    r.set_defaults(func=cmd_lore)

    q.set_defaults(func=cmd_lore)


def _wants_json(args: argparse.Namespace) -> bool:
    """本条命令是否要求 stdout 纯 JSON（供顶层错误出口决定要不要补信封）。"""
    return bool(getattr(args, "json", False))


def _emit_json_failure(code: str, msg: str, extra: dict | None = None) -> None:
    """--json 契约兜底：即使命令内部崩了，stdout 也必须是一枚可 json.loads 的信封。"""
    payload: dict = {"ok": False, "code": code, "error": msg}
    if extra:
        payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    common.reconfigure_utf8()
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args) or 0
    except KeyboardInterrupt:
        print("\n⏸ 已中断（状态文件有原子写保护，重跑 status 看现场）", file=sys.stderr)
        return 130
    except (ValueError, TimeoutError) as exc:
        # 契约修复：错误正文一律走 stderr；--json 时 stdout 补一枚信封。
        # 此前 print 到 stdout，导致 `audit ch_ABC --json` 输出「❌ 无法解析章节号」
        # 纯文本，Agent 侧 json.loads 直接失败。
        if _wants_json(args):
            _emit_json_failure("blocked", str(exc) or exc.__class__.__name__)
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        if _wants_json(args):
            _emit_json_failure("filesystem_error", str(exc))
        print(f"❌ 文件系统错误: {exc}", file=sys.stderr)
        print("   💡 Windows 下常见于文件被占用（杀毒/索引/同步盘）。稍候重试，或关闭占用方后重跑。",
              file=sys.stderr)
        return 1
    except Exception as exc:  # 最后防线：任何漏网异常都不许裸栈穿透到调用方
        # 调试模式下仍把 traceback 打到 stderr（便于排查），但 stdout 保持契约纯净。
        if common.debug_enabled():
            import traceback
            traceback.print_exc(file=sys.stderr)
        if _wants_json(args):
            _emit_json_failure("internal_error", str(exc) or exc.__class__.__name__,
                               {"error_type": type(exc).__name__})
        print(f"❌ 引擎内部错误（{type(exc).__name__}）: {exc}", file=sys.stderr)
        print("   💡 开 NOVEL_STUDIO_DEBUG=1 重跑可看到完整堆栈。", file=sys.stderr)
        return 1
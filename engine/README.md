# engine/ — 确定性引擎（纯 stdlib，零运行时依赖）

入口 `python studio.py <cmd>`（根壳转发 `engine.cli.main`）。引擎只数数与校验，一切需要语义理解和内容识别的判断留给 LLM——
见到"裁决式代码"就是越界。

| 模块 | 职责 | 
|---|---|---|
| cli.py | 10 命令 argparse 目录、闸门与文案、proposal 骨架 |  
| common.py | 工作区定位、JSON 读写（坏文件入 failed/）、幂等登记簿 | 
| state.py | 五表结构、提案合并（upsert/append/resolve…）、**落盘前体检**（verify_data：账本重算/唯一性/实体闭合，任一失败则整体拒绝、不归档、不封存）、空提案 no-op 识别、inbox README 播种 |  
| validator.py + schemas/ | 提案/schema 机械校验（结构级，不判事实真伪） |  
| checks.py | check：结构/schema/算术/逾期/form 占比；sync 前置 `review_gate`（验收覆盖数行） |  
| evidence.py | words/style/form/dup/mentions/gaps/file + all 聚合——只输出数 |  
| pack.py | P0 任务书整块 / P1 触发 / P2 索引，**超预算按优先级硬裁 P2 冷索引**（P0/P1 尽量保留，如实上报 budget）；导出文件名净化 |  
| snapshot.py | 快照 create/list/rollback（pre_rollback 保护；模块不碰 manuscript；CLI 的 --clean-drafts 会额外清理超章稿件） |  

输出契约：数据类命令 stdout 单个 JSON；status/check 为人读表（断言在 test_cli 冻结）。
退出码：0=成功；1=业务拒绝（校验失败/闸门）；2=用法错误。

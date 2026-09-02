# engine/ — 确定性引擎（纯 stdlib，零运行时依赖）

入口 `python studio.py <cmd>`（根壳转发 `engine.cli.main`）。引擎只数数与校验，一切需要语义理解和内容识别的判断留给 LLM——
见到"裁决式代码"就是越界。

| 模块 | 职责 | 
|---|---|
| cli.py | 12 命令 argparse 目录、闸门与文案、proposal 骨架/结构预检、review 校对注记骨架 |  
| common.py | 工作区定位、JSON 读写（坏文件入 failed/）、幂等登记簿 |  
| state.py | 六表结构、提案合并（upsert/append/resolve…；lines 三台账 GUN/MIS/KNO 同生命周期且带权重排序、current 软槽位 mood/goal/key_relationships 原样搬运、entities 支持 item 的 holder/location/condition 并闭合校验 holder）、**落盘前体检**（verify_data：账本重算/唯一性/实体闭合，任一失败则整体拒绝、不归档、不封存）、空提案 no-op 识别、旧文件读时补全（结构键）、inbox README 播种 |  
| validator.py + schemas/ | 提案/schema 机械校验（结构级，不判事实真伪） |  
| checks.py | check：结构/schema/算术/逾期/form 占比 + 上章对照与自交检报数（style_notes_copy/words_band_crowded/acceptance_empty_criterion/line_action_*/retired_entity_on_stage）；sync 可选软提示 `review_gate`（校对注记存在时提示验收覆盖情况，不阻断、不影响退出码）；review 注记骨架数据（`review_skeleton`）、提案三方事实对照（`proposal_cross_facts`，含知识线揭示时机对照） |  
| evidence.py | words/style(含 form 占比)/dup/mentions/gaps/file + candidates（Stage 5 工作单）/prev（Stage 1 上章对照）+ all 聚合——只输出数 |  
| pack.py | P0 热层（含完整 beats）/ P1 触发（人物块含 lines 触碰与随身道具清单 carries；道具块含 holder/location/condition）/ P2 索引，**超预算按优先级硬裁 P2 冷索引**（P0/P1 尽量保留，如实上报 budget）；导出文件名净化 |  
| snapshot.py | 快照 create/list/rollback（pre_rollback 保护；模块不碰 manuscript；CLI 的 --clean-drafts 会额外清理超章稿件） |  
| dashboard.py | 全景可视化看板 HTML 导出（人物关系网、伏笔看板、情绪心电图） |  

输出契约：数据类命令 stdout 单个 JSON；status/check 为人读表。
退出码：0=成功；1=业务拒绝（校验失败/闸门）；2=用法错误。

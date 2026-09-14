---
id: {{slot:faction_id|fac_001}}
name: "{{slot:faction_name|势力/机构/组织/家族全称}}"
type: faction
scale_tier: {{slot:faction_scale_tier|4}}
tier_name: "{{slot:faction_tier_name|行业巨头/区域龙头/核心世家/顶尖大宗}}"
attitude: {{slot:faction_attitude|neutral}}
leader: "{{slot:faction_leader|掌权领袖角色名}}"
headquarters: "{{slot:faction_hq|总部据点/办公大楼/祖庭地名}}"
core_assets:
  - "{{slot:faction_core_asset_1|核心资产/核心竞争力1}}"
  - "{{slot:faction_core_asset_2|主营业务/命脉资源2}}"
diplomacy:
  "{{slot:faction_rival_1|主要竞争/对手名}}": "hostile"
  "{{slot:faction_ally_1|主要合作/盟友名}}": "allied"
status: active
schema_version: novel-studio.faction/v2
---

<!-- 💡【Stage 0 架构师通用指南（填写后可删除本注释）】
     本模板用于记录重要组织、商业集团、家族世家、行业机构或门派势力，适配全题材：
     - 言情/都市：知名企业、顶级律所、家族财团、科研机构、医疗集团；
     - 悬疑/刑侦：专案组、侦探事务所、民间调查网络、行业协会；
     - 玄幻/科幻/历史：传承宗门、星际舰队、门阀世家、商会行帮。
     ★ 规范：组织架构与核心资产清晰明确，未定内容均可写“自行设定”。 -->

# {{slot:faction_name|势力/机构/组织/家族全称}}

---

## 一、 基础档案与组织定位

- **全称与常见简称**：{{slot:faction_name}}（简称：{{slot:faction_short|如：盛天资本 / 水云宫 / 华东研究所（自行设定）}}）
- **规模与行业定位（Scale Tier & Name）**：{{slot:faction_tier_name}}（Scale Tier: {{slot:faction_scale_tier|4}} ｜ 辐射范围：{{slot:faction_coverage|主导某核心行业供应链 / 跨区域运营 / 统辖一方（自行设定）}}）
- **核心特色与专精领域**：{{slot:faction_specialty|专精高端建筑设计 / 量化投资操盘 / 极道修真道统 / 前沿生物科研（自行设定）}}
- **总部所在地与环境**：{{slot:faction_hq}}（{{slot:faction_env|市中心超甲级地标写字楼 / 庄园总舵 / 宗门主峰（自行设定）}}）

---

## 二、 组织架构与核心人物（Hierarchy & Key Figures）

- **最高掌权领袖**：{{slot:faction_leader}}（当前定位：{{slot:faction_leader_realm|董事长 / 掌舵人 / 宗主 / 局长（自行设定）}}）
- **第二序列 / 核心副手**：{{slot:faction_second_in_command|例如：总经理 / 执行董事 / 少掌门 / 首席顾问（自行设定）}}
- **核心团队与执行骨干**：{{slot:faction_elders|各部门总监、核心合伙人、骨干精英团队（自行设定）}}
- **内部发展动态与诉求**：{{slot:faction_internal_strife|新旧业务转型探讨 / 理念分歧 / 稳健开拓（自行设定）}}

---

## 三、 核心资产与竞争壁垒（Core Assets & Defense）

- **核心风控与安全保障**：{{slot:faction_defenses|完善的法务合规体系 / 专属安保网络 / 防护阵列（自行设定）}}
- **核心命脉产业与关键资产（Core Assets）**：
  - 核心资产 1：{{slot:faction_core_asset_1}}
  - 核心资产 2：{{slot:faction_core_asset_2}}
- **精锐团队与执行力量**：{{slot:faction_military|核心专家团队 / 精英行动组 / 骨干力量（自行设定）}}

---

## 四、 合作与竞争网络（Diplomacy Network）

- **主要竞争对手（Hostile / Rival）**：
  - 机构名：{{slot:faction_rival_1}}（竞争焦点：{{slot:faction_rival_cause|市场份额争夺 / 业务竞标 / 理念冲突（自行设定）}}）
- **核心合作伙伴（Allied）**：
  - 机构名：{{slot:faction_ally_1}}（合作基石：{{slot:faction_ally_basis|战略互信 / 互补合作 / 长期契约（自行设定）}}）
- **中立往来方（Neutral）**：
  - {{slot:faction_neutral|行业中介机构 / 评估平台 / 行业协会（自行设定）}}

---

## 五、 重大发展事件记录（Milestones）

- [重要节点] 第 {{slot:fac_event_ch|5}} 章：{{slot:fac_event_desc|完成关键项目签约、化解外部挑战或迎来全新战略突破（自行设定）}}；

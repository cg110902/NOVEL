"""engine.llm — 可插拔 LLM 后端抽象（4.0 全自动核心）。

设计目标：
- 引擎自身不强依赖任何云端 LLM，默认 Mock 生成器就能跑通全流程
- 若检测到环境变量 OPENAI_API_KEY / ANTHROPIC_API_KEY / 本地模型，自动升级
- 所有生成都是确定性 fallback + 随机种子，保证可复现与离线可用

对外接口：
    get_provider() -> LLMProvider
    LLMProvider.generate(prompt, system, max_tokens, temperature) -> str
"""

from __future__ import annotations

import hashlib
import os
import random
import textwrap
from dataclasses import dataclass
from typing import Optional


@dataclass
class LLMResponse:
    text: str
    provider: str
    tokens: int = 0


class LLMProvider:
    """抽象基类"""

    name: str = "base"

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.8,
        **kwargs,
    ) -> LLMResponse:
        raise NotImplementedError

    def is_available(self) -> bool:
        return True


class MockProvider(LLMProvider):
    """离线确定性 Mock - 基于哈希的伪创作，保证全流程可跑"""

    name = "mock"

    # 按题材的语料库，足够让生成不至于太假
    GENRE_TEMPLATES = {
        "玄幻": {
            "world": ["灵气复苏", "大道争锋", "诸天万界", "气运之争"],
            "power": ["炼气", "筑基", "金丹", "元婴", "化神", "渡劫"],
            "conflict": ["宗门大比", "秘境夺宝", "天骄争锋", "气运争夺"],
            "tone": "热血、逆袭、快节奏",
        },
        "仙侠": {
            "world": ["仙凡两隔", "因果轮回", "天道无情", "剑心通明"],
            "power": ["练气", "筑基", "结丹", "元婴", "化神", "炼虚"],
            "conflict": ["问道长生", "斩妖除魔", "心魔劫", "飞升之争"],
            "tone": "飘逸、出尘、宿命感",
        },
        "都市": {
            "world": ["灵气复苏的现代都市", "资本与超凡并存", "暗流涌动的都市传说"],
            "power": ["觉醒者", "异能者", "掌控者", "主宰", "至尊"],
            "conflict": ["商战博弈", "身份曝光", "都市守护", "幕后黑手"],
            "tone": "爽感、反差、接地气",
        },
        "科幻": {
            "world": ["星际殖民", "高维入侵", "AI觉醒", "废土求生"],
            "power": ["星徒", "星士", "星将", "星王", "星帝", "超维"],
            "conflict": ["文明存续", "技术伦理", "星际战争", "真相追寻"],
            "tone": "硬核、悬疑、宏大",
        },
        "悬疑": {
            "world": ["表世界平静，里世界暗流", "每人都有秘密", "真相被层层包裹"],
            "power": ["线索", "推理", "侧写", "局中局"],
            "conflict": ["密室", "人心", "时间闭环", "记忆拼图"],
            "tone": "压抑、烧脑、反转",
        },
        "历史": {
            "world": ["王朝末年", "群雄逐鹿", "庙堂与江湖"],
            "power": ["布衣", "豪强", "诸侯", "帝王"],
            "conflict": ["权谋", "变法", "北伐", "民心"],
            "tone": "厚重、悲壮、家国",
        },
    }

    def __init__(self, seed: str = "novel-studio"):
        self.seed = seed

    def _seeded_random(self, key: str) -> random.Random:
        h = hashlib.md5(f"{self.seed}:{key}".encode()).hexdigest()
        return random.Random(int(h[:8], 16))

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.8,
        **kwargs,
    ) -> LLMResponse:
        # 伪生成：根据 prompt 关键词决定生成类型
        # 实际由上层 generator 模块组装，这里只提供兜底
        rnd = self._seeded_random(prompt[:100])
        # 简单返回 prompt 的改写版本，保证有内容
        lines = []
        if "bible" in prompt.lower() or "世界观" in prompt or "world" in prompt.lower():
            lines.append(f"【世界设定】{prompt[:200]}")
            lines.append("此方世界法则自洽，灵气与因果交织，强者制定规则，弱者寻求破局。")
        elif "角色" in prompt or "character" in prompt.lower():
            lines.append(f"【角色档案】{prompt[:150]}")
            lines.append("外表与内心反差，微动作暴露真实欲望，Want与Fear构成行为引擎。")
        elif "细纲" in prompt or "beats" in prompt.lower():
            lines.append("【本章核心戏剧目标】在既定冲突中制造意外转折，让主角以非常规手段破局。")
            lines.append("场景一：入场铺垫，埋下本章钩子。")
            lines.append("场景二：冲突爆发，情绪台阶递进。")
            lines.append("场景三：断章刀口，卡在悬念引爆瞬间。")
        elif "正文" in prompt or "manuscript" in prompt.lower() or len(prompt) > 500:
            # 正文生成走 generator.py，这里只给占位
            lines.append(prompt[:max_tokens])
        else:
            lines.append(prompt[:max_tokens])

        text = "\n".join(lines)
        # 截断到 max_tokens 估算
        est = len(text) // 2
        if est > max_tokens:
            text = text[: max_tokens * 2]

        return LLMResponse(text=text, provider=self.name, tokens=len(text) // 2)


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.8,
        **kwargs,
    ) -> LLMResponse:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self.api_key)
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            resp = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            txt = resp.choices[0].message.content or ""
            return LLMResponse(text=txt, provider=self.name, tokens=resp.usage.total_tokens if resp.usage else 0)
        except Exception as e:
            # 降级到 mock
            fallback = MockProvider(seed=prompt[:20])
            r = fallback.generate(prompt, system, max_tokens, temperature)
            r.text = f"<!-- openai fallback due to {e} -->\n" + r.text
            r.provider = f"mock(fallback:{e})"
            return r


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-3-5-sonnet-latest"):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, system: str = "", max_tokens: int = 2000, temperature: float = 0.8, **kwargs) -> LLMResponse:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.api_key)
            resp = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system or "你是中文网文创作助手，擅长通俗大白话、高张力叙事。",
                messages=[{"role": "user", "content": prompt}],
            )
            txt = "".join([b.text for b in resp.content if hasattr(b, "text")])
            return LLMResponse(text=txt, provider=self.name, tokens=resp.usage.input_tokens + resp.usage.output_tokens if resp.usage else 0)
        except Exception as e:
            fallback = MockProvider(seed=prompt[:20])
            r = fallback.generate(prompt, system, max_tokens, temperature)
            r.text = f"<!-- anthropic fallback due to {e} -->\n" + r.text
            r.provider = f"mock(fallback:{e})"
            return r


def get_provider(prefer: str = "auto") -> LLMProvider:
    """按环境自动选择最强可用 provider"""
    prefer = (prefer or "auto").lower()

    if prefer == "mock":
        return MockProvider()

    # auto 模式：优先 openai，其次 anthropic，最后 mock
    if prefer in ("auto", "openai"):
        p = OpenAIProvider()
        if p.is_available():
            return p

    if prefer in ("auto", "anthropic", "claude"):
        p = AnthropicProvider()
        if p.is_available():
            return p

    # 检查是否有本地自定义
    if os.getenv("NOVEL_LLM_MOCK_SEED"):
        return MockProvider(seed=os.getenv("NOVEL_LLM_MOCK_SEED"))

    return MockProvider()


# 快捷函数
def generate_text(prompt: str, system: str = "", max_tokens: int = 2000, temperature: float = 0.8, provider: str = "auto") -> str:
    prov = get_provider(provider)
    resp = prov.generate(prompt, system=system, max_tokens=max_tokens, temperature=temperature)
    return resp.text

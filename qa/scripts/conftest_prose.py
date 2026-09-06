"""Prose generator shared by QA scratch builders (mirrors tests/conftest._prose)."""
_BLOCKS = [
    "{hero}把手里的东西翻过来又翻过去，指腹蹭过边缘那道旧痕，心里把账算了一遍。",
    "风从巷口灌进来，卷着水汽，{hero}抬眼看了看檐下那盏灯，影子在墙上抖。",
    "{hero}没说话，只把东西往怀里收了收，眼睛却盯着对面那个人的手。",
    "对方笑了一下，说这个价钱已经是看在老交情上，{hero}再压就没有了。",
    "{hero}点点头，转身走开，走出十几步才回头看了一眼，巷子里已经没人了。",
    "{hero}蹲在台阶上数铜板，数到第三遍才肯信数目对不上，指节捏得发白。",
    "天色擦黑时{hero}绕到茶楼后门，隔着门缝递进去一张纸条，转身就走。",
    "{hero}想起赵七星死前的那个雨夜，灯芯换过一回，这事除了自己没人知道。",
    "主簿那双眼在暗处盯过来时，{hero}后背一紧，面上却笑着把话岔开。",
    "{hero}把密匣压在枕下，翻来覆去到后半夜，终于听见更鼓敲过四下。",
]


def prose_block(n_chars: int, seed: str = "", hero: str = "陆沉舟") -> str:
    """Generate >= n_chars CJK paragraph text mentioning hero often."""
    import random
    rng = random.Random(seed)
    blocks = _BLOCKS[:]
    rng.shuffle(blocks)
    out: list[str] = []
    total = 0
    i = 0
    while total < n_chars:
        s = blocks[i % len(blocks)].format(hero=hero)
        out.append(s)
        total += len(s)
        i += 1
    return "\n\n".join(out)

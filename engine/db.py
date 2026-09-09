"""SQLite3 双平面投影引擎 (Dual-Plane Projection & FTS5 Indexing).

架构原则 (CQRS):
- JSON 为全书唯一的持久权威写模型（Git 友好、原子快照、强 Schema 校验）；
- SQLite (state/.index/book.db) 为只读投影与加速检索缓存，提供百章规模下的 BM25 段落全文检索与 SQL 关系查询；
- 支持随时删除并通过 `python studio.py evidence index --rebuild` 毫秒级重建；
- 零新增外部依赖，使用 Python 标准库 `sqlite3` + `jieba` 分词。
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

try:
    import jieba
    _HAS_JIEBA = True
except ImportError:
    _HAS_JIEBA = False

try:
    from rapidfuzz import fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False

from . import common, state, evidence


INDEX_DIR_NAME = ".index"
DB_NAME = "book.db"

_HAS_FTS5: Optional[bool] = None


def has_fts5() -> bool:
    """检测当前 SQLite 运行时是否支持 FTS5 全文索引扩展。"""
    global _HAS_FTS5
    if _HAS_FTS5 is not None:
        return _HAS_FTS5
    try:
        con = sqlite3.connect(":memory:")
        cur = con.cursor()
        cur.execute("CREATE VIRTUAL TABLE _test_fts USING fts5(c);")
        con.close()
        _HAS_FTS5 = True
    except sqlite3.OperationalError:
        _HAS_FTS5 = False
    return _HAS_FTS5


def register_entities_in_jieba(book: Path) -> None:
    """将全书实体名与别名注入 Jieba 动态词典，保证分词时不被机械切碎。

    必须带专名词性 tag：无 tag 的 add_word 词性为 x，会被 proper_noun_tokens
    的词性闸门滤掉——注入后同进程的专名提取反而认不出实体名（R3 测试暴露）。
    """
    if not _HAS_JIEBA:
        return
    try:
        ents = state.load_state(book, "entities").get("entries", [])
        for e in ents:
            tag = {"person": "nr", "place": "ns", "location": "ns",
                   "faction": "nt"}.get(str(e.get("type", "")), "nz")
            name = str(e.get("name", "")).strip()
            if name and len(name) >= 2:
                jieba.add_word(name, tag=tag)
            for a in (e.get("aliases") or []):
                a_str = str(a).strip()
                if a_str and len(a_str) >= 2:
                    jieba.add_word(a_str, tag=tag)
    except Exception:
        pass


def get_db_path(book: Path) -> Path:
    return Path(book) / "state" / INDEX_DIR_NAME / DB_NAME


def get_connection(book: Path) -> sqlite3.Connection:
    db_path = get_db_path(book)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path), timeout=10.0)
    con.row_factory = sqlite3.Row
    return con


def init_db(book: Path) -> sqlite3.Connection:
    con = get_connection(book)
    cur = con.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        val TEXT
    );
    """)
    if has_fts5():
        cur.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS chapters_fts USING fts5(
            chapter,
            para_idx UNINDEXED,
            text UNINDEXED,
            content
        );
        """)
    else:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS chapters_fts (
            chapter TEXT,
            para_idx INTEGER,
            text TEXT,
            content TEXT
        );
        """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS entities_index (
        name TEXT PRIMARY KEY,
        type TEXT,
        realm TEXT,
        holder TEXT,
        location TEXT,
        charges INTEGER,
        max_charges INTEGER,
        life_status TEXT,
        status TEXT,
        summary TEXT,
        aliases TEXT,
        condition TEXT,
        raw_json TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS lines_index (
        id TEXT PRIMARY KEY,
        kind TEXT,
        name TEXT,
        target_ch INTEGER,
        status TEXT,
        holders TEXT,
        secret TEXT,
        raw_json TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS events_index (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chapter TEXT,
        time TEXT,
        event TEXT,
        quote TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cognition_index (
        id TEXT PRIMARY KEY,
        chapter TEXT,
        character TEXT,
        kind TEXT,
        content TEXT,
        quote TEXT,
        note TEXT
    );
    """)
    # 索引是可丢弃缓存，但旧 DB 可能缺后续新增列；遇到旧库做原地补列，
    # 避免 query_character_pov 等只读路径在未强制重建时直接 SQL 报错。
    _columns = {r["name"] for r in cur.execute("PRAGMA table_info(entities_index)").fetchall()}
    for col, decl in (("condition", "TEXT"), ("raw_json", "TEXT")):
        if col not in _columns:
            cur.execute(f"ALTER TABLE entities_index ADD COLUMN {col} {decl};")
    con.commit()
    return con


def _segment_text(text: str) -> str:
    """对中文文本进行 Jieba 空格分词，供 FTS5 unicode61 索引。"""
    if not text:
        return ""
    if _HAS_JIEBA:
        return " ".join(jieba.cut(text))
    return " ".join(text)


def build_or_update_index(book: Path, force_rebuild: bool = False) -> dict:
    """增量或全量构建 SQLite 检索与投影索引。"""
    t0 = time.perf_counter()
    book = Path(book)
    db_path = get_db_path(book)

    if force_rebuild and db_path.is_file():
        try:
            db_path.unlink()
        except OSError:
            pass

    con = init_db(book)
    register_entities_in_jieba(book)
    cur = con.cursor()

    # 1. 重建或增量更新 chapters_fts
    if force_rebuild:
        cur.execute("DELETE FROM chapters_fts;")

    # 已索引章节的内容哈希（R3：增量按内容比对——旧逻辑按章名跳过，
    # 定稿改后重刷索引会静默沿用旧文，与 finals_fp 指纹撕裂）
    row = cur.execute("SELECT val FROM meta WHERE key='fts_ch_hash';").fetchone()
    try:
        ch_hash = json.loads(row["val"]) if row else {}
        if not isinstance(ch_hash, dict):
            ch_hash = {}
    except (ValueError, TypeError):
        ch_hash = {}

    final_chs = list(evidence.final_chapters(book))
    indexed_ch_count = 0

    for tok, n, text in final_chs:
        ch_tag = f"ch_{n:03d}" if n else tok
        body_hash = common.canonical_json_hash(text)
        if not force_rebuild and ch_hash.get(ch_tag) == body_hash:
            continue
        # 先清除当章已有段落（增量重刷）
        cur.execute("DELETE FROM chapters_fts WHERE chapter = ?;", (ch_tag,))
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        for idx, para in enumerate(paragraphs, start=1):
            segmented = _segment_text(para)
            cur.execute(
                "INSERT INTO chapters_fts(chapter, para_idx, text, content) VALUES (?, ?, ?, ?);",
                (ch_tag, idx, para, segmented)
            )
        ch_hash[ch_tag] = body_hash
        indexed_ch_count += 1

    # 2. 全量刷新 entities_index
    cur.execute("DELETE FROM entities_index;")
    ents = state.load_state(book, "entities").get("entries", [])
    ent_count = 0
    for e in ents:
        name = str(e.get("name", "")).strip()
        if not name:
            continue
        aliases_str = ",".join(str(a) for a in (e.get("aliases") or []) if a)
        cur.execute(
            """INSERT OR REPLACE INTO entities_index
            (name, type, realm, holder, location, charges, max_charges,
             life_status, status, summary, aliases, condition, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
            (
                name,
                e.get("type", "other"),
                e.get("realm"),
                e.get("holder"),
                e.get("location"),
                e.get("charges"),
                e.get("max_charges"),
                e.get("life_status"),
                e.get("status", "active"),
                e.get("summary", ""),
                aliases_str,
                e.get("condition"),
                json.dumps(e, ensure_ascii=False)
            )
        )
        ent_count += 1

    # 3. 全量刷新 lines_index
    cur.execute("DELETE FROM lines_index;")
    lines_st = state.load_state(book, "lines")
    line_count = 0
    for arr, kind in (("foreshadows", "foreshadow"), ("misunderstandings", "misunderstanding"), ("knowledge", "knowledge")):
        for item in lines_st.get(arr, []):
            iid = item.get("id")
            if not iid:
                continue
            holders_str = ",".join(str(h) for h in (item.get("holders") or []) if h)
            name_val = item.get("name") or item.get("content") or item.get("secret") or ""
            cur.execute(
                """INSERT OR REPLACE INTO lines_index
                (id, kind, name, target_ch, status, holders, secret, raw_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);""",
                (
                    iid,
                    kind,
                    name_val,
                    item.get("target_ch"),
                    item.get("status"),
                    holders_str,
                    item.get("secret", ""),
                    json.dumps(item, ensure_ascii=False)
                )
            )
            line_count += 1

    # 4. 刷新 events_index
    cur.execute("DELETE FROM events_index;")
    try:
        tl = state.load_state(book, "timeline")
        for ev in tl.get("events", []):
            cur.execute(
                "INSERT INTO events_index(chapter, time, event, quote) VALUES (?, ?, ?, ?);",
                (ev.get("chapter"), ev.get("time"), ev.get("event"), ev.get("quote", ""))
            )
    except (ValueError, OSError):
        pass

    # 5. 全量刷新 cognition_index
    cur.execute("DELETE FROM cognition_index;")
    cog_count = 0
    try:
        cog_st = state.load_state(book, "cognition")
        for c in cog_st.get("entries", []):
            cid = c.get("id")
            if not cid:
                continue
            cur.execute(
                """INSERT OR REPLACE INTO cognition_index
                (id, chapter, character, kind, content, quote, note)
                VALUES (?, ?, ?, ?, ?, ?, ?);""",
                (
                    cid,
                    c.get("since_ch"),
                    c.get("character"),
                    c.get("kind"),
                    c.get("content"),
                    c.get("quote"),
                    c.get("note")
                )
            )
            cog_count += 1
    except (ValueError, OSError):
        pass

    cur.execute("INSERT OR REPLACE INTO meta(key, val) VALUES ('last_indexed_at', ?);", (str(time.time()),))
    try:
        cur.execute("INSERT OR REPLACE INTO meta(key, val) VALUES ('finals_fp', ?);",
                    (finals_fingerprint(book),))
        cur.execute("INSERT OR REPLACE INTO meta(key, val) VALUES ('fts_ch_hash', ?);",
                    (json.dumps(ch_hash, ensure_ascii=False),))
    except OSError:
        pass
    con.commit()
    # 索引后库里实际有多少章（此前 indexed_chapters 在增量模式下报「本次新刷了几章」、
    # 在 --rebuild 下报「总章数」，同一个字段两种语义，读数的人无从判断）。
    # 必须在 con.close() 之前查。
    try:
        cur.execute("SELECT COUNT(DISTINCT chapter) AS c FROM chapters_fts;")
        total_ch_count = int(cur.fetchone()["c"] or 0)
    except Exception:
        total_ch_count = len(final_chs)
    con.close()

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    return {
        "ok": True,
        "rebuilt": force_rebuild,
        "indexed_chapters": total_ch_count,
        "indexed_chapters_new": indexed_ch_count,
        "indexed_entities": ent_count,
        "indexed_lines": line_count,
        "indexed_cognition": cog_count,
        "time_ms": elapsed_ms,
        "db_path": str(db_path)
    }


def finals_fingerprint(book: Path) -> str:
    """定稿文件指纹（R3）：[(相对路径, mtime_ns, size)] 排序后哈希。

    只读文件元数据、不读内容，供 finals_from_index 做毫秒级新鲜度判定。
    文件选择与 evidence.final_chapters 同源（final_chapter_files）。
    """
    book = Path(book)
    sig = []
    for _vol, _n, p in evidence.final_chapter_files(book):
        try:
            st = p.stat()
            sig.append([str(p.relative_to(book)), st.st_mtime_ns, st.st_size])
        except OSError:
            continue
    return common.canonical_json_hash(sig)


def finals_from_index(book: Path) -> list[tuple[str, int, str]] | None:
    """R3 增量缓存读：指纹命中时从 chapters_fts.text 拼回各章正文。

    返回 [(ch_tag, num, text)]（与 evidence.final_chapters 同形；tok 无卷前缀，
    与 DB 现状 ch_tag 口径一致——跨卷同章号是 DB 预存局限，见 build_or_update）。
    指纹失配/无库/读错一律回 None（调用方回退文件全扫，零行为变更）。
    匹配语义仍是调用方的子串匹配——FTS 只当增量缓存，不当召回器
    （jieba 分词下 MATCH 查全不能保证子串超集，等价性优先）。
    """
    try:
        book = Path(book)
        # 跨卷同章号守卫：DB 章键无卷前缀（预存局限），vol_01/ch_001 与
        # vol_02/ch_001 会互相覆盖只剩其一——此时不用缓存，回退文件扫保正确。
        seen_nums: set[int] = set()
        for _vol, _n, _p in evidence.final_chapter_files(book):
            if _n in seen_nums:
                return None
            seen_nums.add(_n)
        db_path = get_db_path(book)
        if not db_path.is_file():
            return None
        con = sqlite3.connect(str(db_path), timeout=10.0)
        con.row_factory = sqlite3.Row
        try:
            cur = con.cursor()
            row = cur.execute("SELECT val FROM meta WHERE key='finals_fp';").fetchone()
            if row is None or row["val"] != finals_fingerprint(book):
                return None
            rows = cur.execute(
                "SELECT chapter, para_idx, text FROM chapters_fts "
                "ORDER BY chapter, para_idx;").fetchall()
        finally:
            con.close()
        by_ch: dict[str, list[str]] = {}
        for r in rows:
            by_ch.setdefault(str(r["chapter"]), []).append(str(r["text"] or ""))
        out = []
        for tag in sorted(by_ch):
            n = common.chapter_token_to_num(tag)
            if n:
                out.append((tag, n, "\n\n".join(by_ch[tag])))
        return out
    except (sqlite3.Error, OSError, ValueError):
        return None


def search_chapters_bm25(book: Path, query: str, limit: int = 15) -> list[dict]:
    """使用 FTS5 BM25 对全书章节段落执行精准语义检索。"""
    query = str(query or "").strip()
    if not query:
        return []

    db_path = get_db_path(book)
    if not db_path.is_file():
        build_or_update_index(book)

    con = init_db(book)
    cur = con.cursor()

    seg_q = _segment_text(query)
    # FTS5 查询：清洗非法 FTS 特殊字符
    cleaned_tokens = [tok for tok in seg_q.split() if tok and tok not in ("AND", "OR", "NOT", "*", "^")]
    if not cleaned_tokens:
        con.close()
        return []

    if not has_fts5():
        like_pats = [f"%{tok}%" for tok in cleaned_tokens]
        where_clause = " OR ".join(["text LIKE ?" for _ in like_pats])
        try:
            cur.execute(f"SELECT chapter, para_idx, text FROM chapters_fts WHERE {where_clause} LIMIT ?;",
                        (*like_pats, limit * 3))
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            con.close()
            return []
        results = []
        for r in rows:
            ch, p_idx, txt = r["chapter"], r["para_idx"], r["text"]
            fuzz_score = fuzz.partial_ratio(query, txt) if _HAS_RAPIDFUZZ else 60
            results.append({
                "chapter": ch,
                "para_idx": p_idx,
                "text": txt,
                "bm25_rank": 0.0,
                "score": round(fuzz_score / 100.0, 3)
            })
        con.close()
        results.sort(key=lambda x: -x["score"])
        return results[:limit]

    fts_query = " OR ".join(f'"{t}"' for t in cleaned_tokens)
    try:
        cur.execute(
            """SELECT chapter, para_idx, text, rank
            FROM chapters_fts
            WHERE content MATCH ?
            ORDER BY rank
            LIMIT ?;""",
            (fts_query, limit * 2)
        )
        rows = cur.fetchall()
    except sqlite3.OperationalError:
        # FTS 语法容错
        con.close()
        return []

    results = []
    for r in rows:
        ch = r["chapter"]
        p_idx = r["para_idx"]
        txt = r["text"]
        rank = r["rank"]
        # 计算混合相关度 (BM25 rank 是负数，越小越相关)
        fuzz_score = fuzz.partial_ratio(query, txt) if _HAS_RAPIDFUZZ else 50
        norm_rank = 1.0 / (1.0 + abs(rank))
        combined_score = round(norm_rank * 0.4 + (fuzz_score / 100.0) * 0.6, 3)

        results.append({
            "chapter": ch,
            "para_idx": p_idx,
            "text": txt,
            "bm25_rank": round(rank, 4),
            "score": combined_score
        })

    con.close()
    results.sort(key=lambda x: -x["score"])
    return results[:limit]


def query_character_pov(book: Path, name: str) -> dict:
    """从 SQLite 与状态机高效聚合角色第一人称心智模型。"""
    name = str(name or "").strip()
    if not name:
        return {"error": "角色名不能为空"}

    db_path = get_db_path(book)
    if not db_path.is_file():
        build_or_update_index(book)

    # 用 init_db 而非 get_connection：缓存库可能由旧版引擎生成、缺后续新增列，
    # init_db 会做幂等建表 + 补列，避免只读路径直接 SQL 报错。
    con = init_db(book)
    cur = con.cursor()

    # 1. 实体身份与名下资产
    cur.execute("SELECT * FROM entities_index WHERE name = ?;", (name,))
    ent_row = cur.fetchone()
    if not ent_row:
        # 别名查找
        cur.execute("SELECT * FROM entities_index WHERE aliases LIKE ?;", (f"%{name}%",))
        ent_row = cur.fetchone()

    character_info = dict(ent_row) if ent_row else {"name": name, "status": "active"}

    # 名下持有道具
    cur.execute("SELECT name, type, charges, max_charges, condition, summary FROM entities_index WHERE holder = ?;", (name,))
    held_items = [dict(r) for r in cur.fetchall()]

    # 2. 角色认知 (cognition)——cognition_index 把 since_ch 存进 chapter 列
    cur.execute("SELECT id, chapter AS since_ch, kind, content, quote, note FROM cognition_index WHERE character = ?;", (name,))
    cogs = [dict(r) for r in cur.fetchall()]

    known_facts = [c for c in cogs if c["kind"] in ("fact", "secret_known")]
    suspicions = [c for c in cogs if c["kind"] == "suspicion"]
    misunderstandings = [c for c in cogs if c["kind"] == "misunderstanding"]

    # 3. 角色知情线与被瞒秘密
    cur.execute("SELECT id, kind, name, status, holders, secret FROM lines_index WHERE kind = 'knowledge';")
    kno_rows = cur.fetchall()
    secrets_held = []
    secrets_concealed_from_character = []

    for kr in kno_rows:
        holders = [h.strip() for h in (kr["holders"] or "").split(",") if h.strip()]
        if name in holders or any(name in h for h in holders):
            secrets_held.append({
                "id": kr["id"],
                "secret": kr["secret"] or kr["name"],
                "status": kr["status"]
            })
        else:
            if kr["status"] != "Revealed":
                secrets_concealed_from_character.append({
                    "id": kr["id"],
                    "secret_topic": kr["name"] or "核心机密",
                    "status": "对该角色完全保密（严防上帝视角）"
                })

    con.close()

    return {
        "character": name,
        "profile": {
            "type": character_info.get("type"),
            "realm": character_info.get("realm"),
            "location": character_info.get("location"),
            "life_status": character_info.get("life_status", "alive"),
            "summary": character_info.get("summary")
        },
        "held_assets": held_items,
        "cognition": {
            "facts": known_facts,
            "suspicions": suspicions,
            "misunderstandings": misunderstandings
        },
        "knowledge_matrix": {
            "secrets_held": secrets_held,
            "concealed_from_character": secrets_concealed_from_character
        }
    }
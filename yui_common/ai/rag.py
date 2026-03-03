from datetime import date
from yui_common.db.session import get_async_session
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import cast
from pgvector.sqlalchemy import Vector
from pgvector.asyncpg import register_vector
from yui_common.ai.chat_client import YuiAIChatClient

###############################
# 一日まとめてドン！（初期RAG、休止20260129）
###############################
async def generate_rag_snippet(
        session: AsyncSession, 
        syokuin_cd: str, 
        report_date: date | None = None,
        kojin_id: int | None = None, 
        setai_id: int | None = None, 
        branch_cd: str | None = None
        ):

    import os
    import traceback

    print("===== RAG DEBUG generate_rag_snippet =====")
    print("YUI_AI_BASE_URL =", os.getenv("YUI_AI_BASE_URL"))
    traceback.print_stack()
    print("=====================")

    conn = await session.connection()
    raw_conn = await conn.get_raw_connection()
    pgconn = raw_conn._connection  # ← 裏技だが実際これしかない
    await register_vector(pgconn)

    snippets = []

    # 利用者ノート（note_type='note'、削除されてない）
    rows = await session.execute(text("""
        SELECT id, note_text, setai_id, syokuin_name
        FROM app.note
        WHERE kojin_id = :kojin_id
          AND report_date = :report_date
          AND target_type = 'riyosya'
          AND delete_flag = false
          AND syokuin_cd = :syokuin_cd
    """), {"kojin_id": kojin_id, "report_date": report_date, "syokuin_cd": syokuin_cd})

    for row in rows:
        if row.note_text.strip():
            snippets.append({
                "source_type": "riyosya",
                "source_id": row.id,
                "content": row.note_text.strip(),
                "setai_id": row.setai_id,
                "syokuin_name": row.syokuin_name,
            })

    # 職員ノート（note_type='siten'、削除されてない）
    rows = await session.execute(text("""
        SELECT id, note_text, setai_id, syokuin_name
        FROM app.note
        WHERE report_date = :report_date
          AND target_type = 'syokuin'
          AND delete_flag = false
          AND syokuin_cd = :syokuin_cd
    """), {"report_date": report_date, "syokuin_cd": syokuin_cd})

    for row in rows:
        if row.note_text.strip():
            snippets.append({
                "source_type": "syokuin",
                "source_id": row.id,
                "content": row.note_text.strip(),
                "setai_id": row.setai_id,
                "syokuin_name": row.syokuin_name,
            })

    # リマインダー
    rows = await session.execute(text("""
        SELECT reminder_id, description, syokuin_name
        FROM app.reminder
        WHERE kojin_id = :kojin_id
          AND event_date = :report_date
          AND syokuin_cd = :syokuin_cd
    """), {"kojin_id": kojin_id, "report_date": report_date, "syokuin_cd": syokuin_cd})

    for row in rows:
        if row.description and row.description.strip():
            snippets.append({
                "source_type": "reminder",
                "source_id": row.reminder_id,
                "content": row.description.strip(),
                "setai_id": None,
                "syokuin_name": row.syokuin_name,
            })

    # 世帯ノート（setai_id取得 → 日付一致する created_at or updated_at）
    rows = await session.execute(text("""
        SELECT id, setai_id, note_text, syokuin_name
        FROM app.setai_note
        WHERE setai_id = (
            SELECT setai_id FROM kdp.master_kojin WHERE kojin_id = :kojin_id LIMIT 1
        )
        AND DATE(updated_at) = :report_date
    """), {"kojin_id": kojin_id, "report_date": report_date})

    for row in rows:
        if row.note_text.strip():
            snippets.append({
                "source_type": "setai",
                "source_id": row.id,
                "content": row.note_text.strip(),
                "setai_id": row.setai_id,
                "syokuin_name": row.syokuin_name,
            })

    # マイノート（syokuin_cd取得）
    rows = await session.execute(text("""
        SELECT private_note_id, syokuin_cd, note_text, syokuin_name
        FROM app.private_note
        WHERE syokuin_cd = :syokuin_cd
        AND DATE(note_date) = :report_date
    """), {"syokuin_cd": syokuin_cd, "report_date": report_date})

    for row in rows:
        if row.note_text.strip():
            snippets.append({
                "source_type": "mynote",
                "source_id": row.private_note_id,
                "content": row.note_text.strip(),
                "setai_id": None,
                "syokuin_name": row.syokuin_name,
            })


    # スニペット生成と登録（まずDELETEで消す）
    for snip in snippets:
        await session.execute(text("""
            DELETE FROM ai.rag_snippets
            WHERE source_type = :source_type AND source_id = :source_id
        """), {"source_type": snip["source_type"], "source_id": snip["source_id"]})

        # inside loop
        embedding = await embed_text(snip["content"])

        await session.execute(text("""
            INSERT INTO ai.rag_snippets (
                kojin_id, setai_id, source_type, source_id,
                content, embedding, report_date,
                syokuin_cd, syokuin_name
            )
            VALUES (
                :kojin_id, :setai_id, :source_type, :source_id,
                :content, :embedding, :report_date,
                :syokuin_cd, :syokuin_name
            )
        """), {
            "kojin_id": kojin_id,
            "setai_id": snip["setai_id"],
            "source_type": snip["source_type"],
            "source_id": snip["source_id"],
            "content": snip["content"],
            "embedding": embedding,  # ここは list[float]
            "report_date": report_date,
            "syokuin_cd": syokuin_cd,
            "syokuin_name": snip["syokuin_name"]
        })



import os
import asyncio
import requests

YUI_AI_BASE_URL = os.getenv(
    "YUI_AI_BASE_URL",
    "http://yui-ai:8000"   # docker 内通信
)

async def embed_text(text: str) -> list[float]:
    """
    yui-ai に埋め込み生成を依頼する（async対応）
    """
    def _call_api():

        import os
        import traceback

        print("===== RAG DEBUG _call_api =====")
        print("YUI_AI_BASE_URL =", os.getenv("YUI_AI_BASE_URL"))
        traceback.print_stack()
        print("=====================")

        r = requests.post(
            f"{YUI_AI_BASE_URL}/embed/",
            json={"text": text},
            timeout=10,
        )
        r.raise_for_status()
        return r.json()["embedding"]

    return await asyncio.to_thread(_call_api)


###############################
# 利用者ノートをRAGに突っ込む
###############################
async def generate_rag_snippet_riyosya(
    session: AsyncSession,
    note_id: int,
):
    conn = await session.connection()
    raw_conn = await conn.get_raw_connection()
    pgconn = raw_conn._connection
    await register_vector(pgconn)

    result = await session.execute(text("""
        SELECT
            n.id,
            n.note_text,
            n.kojin_id,
            n.setai_id,
            n.syokuin_cd,
            n.syokuin_name,
            n.report_date,
            k."氏名" AS kojin_name
        FROM app.note n
        LEFT JOIN kdp.master_kojin k
            ON n.kojin_id = k.kojin_id
        WHERE n.id = :id
        AND n.delete_flag = false
        AND n.target_type = 'riyosya'
    """), {"id": note_id})


    row = result.mappings().first()
    if not row or not row["note_text"].strip():
        return

    kojin_name = row["kojin_name"] or "不明"

    content = f"""
    【{kojin_name}の利用者ノート】
    氏名: {kojin_name}
    記録者: {row["syokuin_name"]}
    日付: {row["report_date"]}
    内容:
    {row["note_text"].strip()}
    """.strip()

    embedding = await embed_text(content)
    snippet_type = await classify_snippet_type(content)
    importance = calculate_importance(content, snippet_type)  # ← ここ追加

    await session.execute(text("""
        INSERT INTO ai.rag_snippets (
            snippet_type,
            kojin_id,
            setai_id,
            source_type,
            source_id,
            content,
            embedding,
            report_date,
            syokuin_cd,
            syokuin_name,
            importance_score,
            updated_at
        )
        VALUES (
            :snippet_type,
            :kojin_id,
            :setai_id,
            'riyosya',
            :source_id,
            :content,
            :embedding,
            :report_date,
            :syokuin_cd,
            :syokuin_name,
            :importance_score,
            now()
        )
        ON CONFLICT (source_type, source_id)
        DO UPDATE SET
            content = EXCLUDED.content,
            embedding = EXCLUDED.embedding,
            snippet_type = EXCLUDED.snippet_type,
            report_date = EXCLUDED.report_date,
            syokuin_cd = EXCLUDED.syokuin_cd,
            syokuin_name = EXCLUDED.syokuin_name,
            importance_score = EXCLUDED.importance_score,
            updated_at = now()
    """), {
        "snippet_type": snippet_type,
        "kojin_id": row["kojin_id"],
        "setai_id": row["setai_id"],
        "source_id": row["id"],
        "content": content,
        "embedding": embedding,
        "report_date": row["report_date"],
        "syokuin_cd": row["syokuin_cd"],
        "syokuin_name": row["syokuin_name"],
        "importance_score": importance,
    })


###############################
# 職員ノートをRAGに突っ込む
###############################
async def generate_rag_snippet_syokuin(
    session: AsyncSession,
    note_id: int,
):
    conn = await session.connection()
    raw_conn = await conn.get_raw_connection()
    pgconn = raw_conn._connection
    await register_vector(pgconn)

    result = await session.execute(text("""
        SELECT
            id,
            note_text,
            kojin_id,
            setai_id,
            syokuin_cd,
            syokuin_name,
            report_date
        FROM app.note
        WHERE id = :id
        AND target_type = 'syokuin'
    """), {"id": note_id})

    row = result.mappings().first()
    if not row or not row["note_text"] or not row["note_text"].strip():
        return

    content = f"""
    【職員ノート】
    記録者: {row["syokuin_name"]}
    日付: {row["report_date"]}
    内容:
    {row["note_text"].strip()}
    """.strip()

    embedding = await embed_text(content)
    snippet_type = await classify_snippet_type(content)
    importance = calculate_importance(content, snippet_type)  # ← 追加

    await session.execute(text("""
        INSERT INTO ai.rag_snippets (
            snippet_type,
            kojin_id,
            setai_id,
            source_type,
            source_id,
            content,
            embedding,
            report_date,
            syokuin_cd,
            syokuin_name,
            importance_score,
            updated_at
        )
        VALUES (
            :snippet_type,
            :kojin_id,
            :setai_id,
            'syokuin',
            :source_id,
            :content,
            :embedding,
            :report_date,
            :syokuin_cd,
            :syokuin_name,
            :importance_score,
            now()
        )
        ON CONFLICT (source_type, source_id)
        DO UPDATE SET
            content = EXCLUDED.content,
            embedding = EXCLUDED.embedding,
            snippet_type = EXCLUDED.snippet_type,
            report_date = EXCLUDED.report_date,
            syokuin_cd = EXCLUDED.syokuin_cd,
            syokuin_name = EXCLUDED.syokuin_name,
            importance_score = EXCLUDED.importance_score,
            updated_at = now()
    """), {
        "snippet_type": snippet_type,
        "kojin_id": row["kojin_id"],
        "setai_id": row["setai_id"],
        "source_id": row["id"],
        "content": content,
        "embedding": embedding,
        "report_date": row["report_date"],
        "syokuin_cd": row["syokuin_cd"],
        "syokuin_name": row["syokuin_name"],
        "importance_score": importance,
    })


###############################
# リマインダーをRAGに突っ込む
###############################
async def generate_rag_snippet_reminder(
    session: AsyncSession,
    note_id: int,
):
    conn = await session.connection()
    raw_conn = await conn.get_raw_connection()
    pgconn = raw_conn._connection
    await register_vector(pgconn)

    result = await session.execute(text("""
        SELECT
            r.reminder_id AS id,
            r.description AS note_text,
            r.kojin_id,
            0 AS setai_id,
            r.syokuin_cd,
            r.syokuin_name,
            r.event_date AS report_date,
            k."氏名" AS kojin_name
        FROM app.reminder r
        LEFT JOIN kdp.master_kojin k
            ON r.kojin_id = k.kojin_id
        WHERE r.reminder_id = :id
    """), {"id": note_id})


    row = result.mappings().first()
    if not row or not row["note_text"] or not row["note_text"].strip():
        return

    kojin_name = row["kojin_name"] or "不明"

    content = f"""
    【{kojin_name}の予定】
    氏名: {kojin_name}
    記録者: {row["syokuin_name"]}
    予定日: {row["report_date"]}
    内容:
    {row["note_text"].strip()}
    """.strip()

    embedding = await embed_text(content)
    snippet_type = await classify_snippet_type(content)
    importance = calculate_importance(content, snippet_type)

    await session.execute(text("""
        INSERT INTO ai.rag_snippets (
            snippet_type,
            kojin_id,
            setai_id,
            source_type,
            source_id,
            content,
            embedding,
            report_date,
            syokuin_cd,
            syokuin_name,
            importance_score,
            updated_at
        )
        VALUES (
            :snippet_type,
            :kojin_id,
            :setai_id,
            'reminder',
            :source_id,
            :content,
            :embedding,
            :report_date,
            :syokuin_cd,
            :syokuin_name,
            :importance_score,
            now()
        )
        ON CONFLICT (source_type, source_id)
        DO UPDATE SET
            content = EXCLUDED.content,
            embedding = EXCLUDED.embedding,
            snippet_type = EXCLUDED.snippet_type,
            report_date = EXCLUDED.report_date,
            syokuin_cd = EXCLUDED.syokuin_cd,
            syokuin_name = EXCLUDED.syokuin_name,
            importance_score = EXCLUDED.importance_score,
            updated_at = now()
    """), {
        "snippet_type": snippet_type,
        "kojin_id": row["kojin_id"],
        "setai_id": row["setai_id"],
        "source_id": row["id"],
        "content": content,
        "embedding": embedding,
        "report_date": row["report_date"],
        "syokuin_cd": row["syokuin_cd"],
        "syokuin_name": row["syokuin_name"],
        "importance_score": importance,
    })


###########################################
# RAGに突っ込むimportanceをルールベースで判断させる
###########################################
def calculate_importance(content: str, snippet_type: str) -> float:
    score = 0.3  # base

    # 1. snippet_type補正
    type_weight = {
        "decision": 0.4,
        "change": 0.3,
        "emotion": 0.1,
        "fact": 0.0
    }
    score += type_weight.get(snippet_type, 0.0)

    # 2. キーワード補正
    keyword_groups = {
        0.4: ["クレーム", "苦情", "他JA", "解約"],
        0.4: ["結い", "訪問", "メール", "見積", "請求", "支払"],
        0.3: ["相続", "後継", "廃業", "倒れ", "病気"],
        0.3: ["電話", "相談", "ミーティング"],
        0.2: ["検討", "相談", "見直し", "契約予定"],
        0.0: ["世帯を追加", "世帯員を追加"],
    }

    for weight, words in keyword_groups.items():
        if any(word in content for word in words):
            score += weight
            break  # 一番重いものだけ加算

    return min(score, 1.0)


###########################################
# RAGに突っ込むスニペットタイプをLLMに判断させる
###########################################
async def classify_snippet_type(text: str) -> str:
    ai_client = YuiAIChatClient(
    base_url=os.getenv("YUI_AI_BASE_URL", "http://yui-ai:8000")
)
    prompt = f"""
次の文章はJA職員の業務記録の一部です。
内容の性質として最も近いものを、次から1つだけ選んでください。

- decision
- change
- emotion
- fact

文章：
{text}

出力はラベル名のみ。
"""

    messages = [
        {
            "role": "system",
            "content": "あなたは業務記録を分類するアシスタントです。"
        },
        {
            "role": "user",
            "content": prompt
        }
    ]

    answer = ai_client.chat(
        messages=messages,
        temperature=0.0
    )

    label = answer.strip().lower()
    return label if label in {"decision","change","emotion","fact"} else "fact"



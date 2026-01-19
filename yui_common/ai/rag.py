from datetime import date
from common.db.session import get_async_session
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import cast
from pgvector.sqlalchemy import Vector
from pgvector.asyncpg import register_vector


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




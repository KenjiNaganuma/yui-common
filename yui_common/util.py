# ModuleUtil.py
import os
import importlib.util
from collections import defaultdict
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from pathlib import Path
from sqlalchemy import text
from fastapi import FastAPI, Request, Form, Depends, Query

print("✅ util.py 実体:", __file__)

# BASE_DIR = Path(__file__).resolve().parent
# CONFIG_PATH = BASE_DIR / "aianalyzer_config.py"


# module_util.py のグローバル定数として
DEFAULT_USER_ID = 1111
DEFAULT_USER_NAME = "亜久里　旬"



# -----------------------------------------------------------------------------------
# config 読み込み
# -----------------------------------------------------------------------------------
from pathlib import Path

################################
# 画面遷移パラメータ保存クラス
################################
from typing import Optional
class EventFormParams:
    def __init__(
        self,
        hidden_start_date: str = Form(None),
        hidden_end_date: str = Form(None),
        hidden_note_date: str = Form(None),
        hidden_login_syokuin_cd: str = Form(None),
        hidden_login_syokuin_name: str = Form(None),
        hidden_selected_syokuin_cd: str = Form(None),
        hidden_selected_report: str = Form(None),
        hidden_search_word: str = Form(None),
        hidden_selected_tag: str = Form(None),
        hidden_selected_tag_type: str = Form(None),
        hidden_selected_kojin_id: str = Form(None),
    ):
        self.hidden_start_date: Optional[str] = hidden_start_date
        self.hidden_end_date: Optional[str] = hidden_end_date
        self.hidden_note_date: Optional[str] = hidden_note_date
        self.hidden_login_syokuin_cd: Optional[str] = hidden_login_syokuin_cd
        self.hidden_login_syokuin_name: Optional[str] = hidden_login_syokuin_name
        self.hidden_selected_syokuin_cd: Optional[str] = hidden_selected_syokuin_cd
        self.hidden_selected_report: Optional[str] = hidden_selected_report
        self.hidden_search_word: Optional[str] = hidden_search_word
        self.hidden_selected_tag: Optional[str] = hidden_selected_tag
        self.hidden_selected_tag_type: Optional[str] = hidden_selected_tag_type
        self.hidden_selected_kojin_id: Optional[str] = hidden_selected_kojin_id



#######################################
#   閲覧ログを取得
#######################################
from sqlalchemy import text

async def get_recent_logs_session(session, syokuin_cd):
    result = await session.execute(text("""
        WITH latest_logs AS (
            SELECT DISTINCT ON (a.kojin_id)
                a.kojin_id, 
                k."氏名", 
                a.timestamp
            FROM app.access_log a
            JOIN kdp.master_kojin k ON k.kojin_id = a.kojin_id
            WHERE a.syokuin_cd = :syokuin_cd
            ORDER BY a.kojin_id, a.timestamp DESC
        )
        SELECT * FROM latest_logs
        ORDER BY timestamp DESC
        LIMIT 10;
    """), {"syokuin_cd": syokuin_cd})

    logs = result.fetchall()
    recent_logs = [
        {
            "kojin_id": row[0],
            "name": row[1],
            "timestamp": row[2],
            "timestamp_row": row[2]
        }
        for row in logs
    ]

    grouped_logs = defaultdict(list)
    for log in recent_logs:
        date = log["timestamp_row"].date()
        grouped_logs[date].append(log)

    return sorted(grouped_logs.items(), reverse=True)


#######################################
#   ログイン職員情報を取得
#######################################
async def get_syokuin_by_cd(session: AsyncSession, syokuin_cd: str) -> dict | None:
    """
    職員CDから master_syokuin の1件を取得し、dict で返す。
    """
    if not syokuin_cd:
        return None

    sql = text("""
        SELECT *
        FROM kdp.master_syokuin
        WHERE syokuin_cd = :syokuin_cd
          AND is_active = true
        LIMIT 1
    """)

    result = await session.execute(sql, {"syokuin_cd": syokuin_cd})
    row = result.fetchone()

    return dict(row._mapping) if row else None


# -----------------------------------
#   FastAPI用テンプレート共通定義
# -----------------------------------
# from pathlib import Path
# from fastapi.templating import Jinja2Templates

# main.py に移動
# BASE_DIR = Path(__file__).resolve().parent.parent
# TEMPLATE_DIR = BASE_DIR / "templates"
# print("🧭 TEMPLATE SEARCH PATH → ", TEMPLATE_DIR)

# templates = Jinja2Templates(directory=TEMPLATE_DIR)
# ✅ ここに get_login_user を設定！！
# templates.env.globals["get_syokuin"] = lambda request: getattr(request.state, "syokuin", None)
# templates.env.filters["tag_linkify"] = tag_linkify  # ← ここでOK！！


#######################################
#   タグ追加
#######################################
async def tag_insert(
    syokuin_cd: str,
    syokuin_name: str,
    target_type: str,
    target_id: int,
    tags: set[str],
    session: AsyncSession,
    tag_type: str = 'private'
):
    for tag in tags:
        # 🔍 共有タグは全職員で同名チェック
        if tag_type == 'shared':
            result = await session.execute(text("""
                SELECT tag_id 
                FROM app.tag_master
                WHERE tag_name = :tag_name 
                AND tag_type = 'shared'
            """), {
                "tag_name": tag
            })
        else:
            # プライベートタグは職員ごとにチェック
            result = await session.execute(text("""
                SELECT tag_id 
                FROM app.tag_master
                WHERE tag_name = :tag_name 
                AND tag_type = :tag_type 
                AND syokuin_cd = :syokuin_cd
            """), {
                "tag_name": tag,
                "tag_type": tag_type,
                "syokuin_cd": syokuin_cd
            })

        tag_id = result.scalar()

        # 💾 新規なら追加 tag_master
        if not tag_id:
            res = await session.execute(text("""
                INSERT INTO app.tag_master 
                (tag_name, tag_type, syokuin_cd, syokuin_name)
                VALUES 
                (:tag_name, :tag_type, :syokuin_cd, :syokuin_name)
                RETURNING tag_id
            """), {
                "tag_name": tag,
                "tag_type": tag_type,
                "syokuin_cd": syokuin_cd,
                "syokuin_name": syokuin_name
            })
            tag_id = res.scalar()

        # 🔗 tag_link 追加（毎回）
        await session.execute(text("""
            INSERT INTO app.tag_link 
            (tag_id, target_type, target_id, syokuin_cd, syokuin_name)
            VALUES 
            (:tag_id, :target_type, :target_id, :syokuin_cd, :syokuin_name)
        """), {
            "tag_id": tag_id,
            "target_type": target_type,
            "target_id": target_id,
            "syokuin_cd": syokuin_cd,
            "syokuin_name": syokuin_name
        })





async def tag_update(syokuin_cd: str, syokuin_name: str, target_type: str, target_id: int, tags: set[str], session: AsyncSession, tag_type: str = 'private'):
    # 既存タグを取得
    result = await session.execute(text("""
        SELECT tm.tag_name
        FROM app.tag_link tl
        JOIN app.tag_master tm ON tl.tag_id = tm.tag_id
        WHERE tl.target_type = :target_type
        AND tl.target_id = :target_id 
        AND tl.syokuin_cd = :syokuin_cd 
        AND tm.tag_type = :tag_type
    """), {
        "target_type": target_type,
        "target_id": target_id,
        "syokuin_cd": syokuin_cd,
        "tag_type": tag_type
    })
    current_tags = set(row[0] for row in result.fetchall())

    # 差分
    to_add = tags - current_tags
    to_remove = current_tags - tags

    await tag_delete(syokuin_cd, target_type, target_id, to_remove, session, tag_type=tag_type)
    await tag_insert(syokuin_cd, syokuin_name, target_type, target_id, to_add, session, tag_type=tag_type)
    


async def tag_delete(
    syokuin_cd: str,
    target_type: str,
    target_id: int,
    tags: set[str],
    session: AsyncSession,
    tag_type: str = 'private'
):
    if not tags:
        return  # 念のため空なら即帰る

    for tag in tags:
        await session.execute(text("""
            DELETE FROM app.tag_link tl
            USING app.tag_master tm
            WHERE tl.tag_id = tm.tag_id
              AND tm.tag_name = :tag_name
              AND tl.syokuin_cd = :syokuin_cd
              AND tm.tag_type = :tag_type
              AND tl.target_type = :target_type
              AND tl.target_id = :target_id
        """), {
            "tag_name": tag,
            "target_type": target_type,
            "target_id": target_id,
            "tag_type": tag_type,
            "syokuin_cd": syokuin_cd
        })


# -----------------------------------------------------------------------------------
# ログ表示と保存
# -----------------------------------------------------------------------------------
from datetime import datetime
def echo_log(message, log_path="ainote_log.txt", show_console=True):
    timestamp = datetime.now().strftime("🕒[%H:%M:%S] ")
    line = f"{timestamp}{message}"

    if show_console:
        print(line)

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")

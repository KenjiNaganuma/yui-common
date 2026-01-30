# yui_common/middleware/auth.py
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text
from yui_common.db.session import get_sessionmaker

class LoginUserMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):

        request.state.syokuin = None

        if hasattr(request, "session"):
            syokuin_cd = request.session.get("syokuin_cd")

            if syokuin_cd:
                SessionLocal = get_sessionmaker()   # ← ① sessionmaker を取得
                async with SessionLocal() as db:     # ← ② AsyncSession を生成して with
                    result = await db.execute(
                        text("""
                            SELECT *
                            FROM kdp.master_syokuin
                            WHERE syokuin_cd = :cd
                        """),
                        {"cd": syokuin_cd}
                    )
                    row = result.fetchone()
                    if row:
                        request.state.syokuin = dict(row._mapping)

        return await call_next(request)

# yui_common/middleware/auth.py
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text
from yui_common.db.session import get_sessionmaker
import logging

# ログのフォーマット
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(process)d] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logger = logging.getLogger(__name__)

class LoginUserMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        logger.info(f"🔥 LoginUserMiddleware HIT path={request.url.path}")

        request.state.syokuin = None

        session = request.scope.get("session")
        logger.info(f"🔥 session in middleware = {session}")

        # ★ ここだけを見る
        syokuin_cd = session.get("syokuin_cd") if session is not None else None
        logger.info(f"🔥 syokuin_cd from session = {syokuin_cd}")

        if syokuin_cd:
            SessionLocal = get_sessionmaker()
            async with SessionLocal() as db:
                result = await db.execute(
                    text("""
                        SELECT *
                        FROM kdp.master_syokuin
                        WHERE syokuin_cd = :cd
                    """),
                    {"cd": syokuin_cd}
                )
                row = result.fetchone()
                logger.info(f"🔥 DB row = {row}")

                if row:
                    request.state.syokuin = dict(row._mapping)

        return await call_next(request)


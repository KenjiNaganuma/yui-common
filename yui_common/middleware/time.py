# middleware/server_time.py
from datetime import datetime
from zoneinfo import ZoneInfo
from starlette.middleware.base import BaseHTTPMiddleware

JST = ZoneInfo("Asia/Tokyo")

class ServerTimeMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request.state.server_now = datetime.now(JST)
        return await call_next(request)

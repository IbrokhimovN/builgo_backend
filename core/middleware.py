# Middleware removed — authentication is now handled via JWT (SimpleJWT).
# The old TelegramAuthMiddleware has been replaced by:
# 1. POST /api/telegram-auth/ — verifies Telegram initData and returns JWT tokens
# 2. JWT Bearer token in Authorization header for all protected endpoints

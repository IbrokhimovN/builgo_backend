"""
Authentication for BuildGo Backend.

Two authentication strategies (NO User model, NO JWT):

1. TelegramInitDataAuthentication
   - For Mini App (WebApp) requests
   - Verifies Telegram initData via HMAC-SHA256
   - Extracts telegram_id from verified payload

2. BotSecretAuthentication
   - For Bot → API calls
   - Shared secret header verification

Role logic is NOT touched. telegram_id resolution stays per-request.
"""

import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qs, unquote

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)

# initData is valid for 5 minutes (300 seconds)
INIT_DATA_MAX_AGE = 300


class TelegramUser:
    """
    Lightweight user-like object for DRF.
    NOT a Django User. Just carries telegram_id for request context.
    """

    def __init__(self, telegram_id: int):
        self.telegram_id = telegram_id
        self.is_authenticated = True

    def __str__(self):
        return f"TelegramUser({self.telegram_id})"


class TelegramInitDataAuthentication(BaseAuthentication):
    """
    Authenticate Mini App requests using Telegram initData.

    The Mini App frontend sends the raw initData string in:
        X-Telegram-Init-Data: <initData>

    Verification follows Telegram's official algorithm:
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """

    def authenticate(self, request):
        init_data = request.META.get("HTTP_X_TELEGRAM_INIT_DATA")
        if not init_data:
            return None  # Let other auth classes try

        bot_token = settings.TELEGRAM_BOT_TOKEN
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not configured")
            raise AuthenticationFailed("Server configuration error")

        try:
            telegram_id = self._verify_init_data(init_data, bot_token)
        except AuthenticationFailed:
            raise
        except Exception as e:
            logger.exception("Unexpected error verifying initData")
            raise AuthenticationFailed("Invalid authentication data")

        user = TelegramUser(telegram_id)
        request.telegram_id = telegram_id
        return (user, None)

    def _verify_init_data(self, init_data: str, bot_token: str) -> int:
        """
        Verify initData HMAC-SHA256 signature and extract telegram_id.

        Algorithm:
        1. Parse initData as query string
        2. Extract and remove 'hash' parameter
        3. Sort remaining params alphabetically
        4. Build data-check-string: "key=value\\n" pairs
        5. Compute HMAC-SHA256(secret_key, data_check_string)
           where secret_key = HMAC-SHA256("WebAppData", bot_token)
        6. Compare computed hash with received hash
        7. Check auth_date is not too old
        8. Extract user.id as telegram_id
        """
        parsed = parse_qs(init_data, keep_blank_values=True)

        # Each value in parse_qs is a list; take first element
        flat = {}
        for key, values in parsed.items():
            flat[key] = values[0] if values else ""

        received_hash = flat.pop("hash", None)
        if not received_hash:
            raise AuthenticationFailed("Missing hash in initData")

        # Build data-check-string
        data_check_parts = sorted(
            f"{key}={value}" for key, value in flat.items()
        )
        data_check_string = "\n".join(data_check_parts)

        # Compute secret key
        secret_key = hmac.new(
            b"WebAppData", bot_token.encode(), hashlib.sha256
        ).digest()

        # Compute hash
        computed_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(computed_hash, received_hash):
            raise AuthenticationFailed("Invalid initData signature")

        # Check auth_date freshness
        auth_date_str = flat.get("auth_date")
        if auth_date_str:
            try:
                auth_date = int(auth_date_str)
                if time.time() - auth_date > INIT_DATA_MAX_AGE:
                    raise AuthenticationFailed("initData expired")
            except ValueError:
                raise AuthenticationFailed("Invalid auth_date")

        # Extract telegram_id from user field
        user_data = flat.get("user")
        if not user_data:
            raise AuthenticationFailed("Missing user in initData")

        try:
            user_obj = json.loads(unquote(user_data))
            telegram_id = int(user_obj["id"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            raise AuthenticationFailed("Invalid user data in initData")

        return telegram_id


class BotSecretAuthentication(BaseAuthentication):
    """
    Authenticate Bot → API calls using a shared secret header.

    The bot sends:
        X-Bot-Secret: <shared_secret>

    Backend compares against BOT_API_SECRET from settings.
    """

    def authenticate(self, request):
        secret = request.META.get("HTTP_X_BOT_SECRET")
        if not secret:
            return None  # Let other auth classes try

        expected = getattr(settings, "BOT_API_SECRET", None)
        if not expected:
            logger.error("BOT_API_SECRET not configured")
            raise AuthenticationFailed("Server configuration error")

        if not hmac.compare_digest(secret, expected):
            raise AuthenticationFailed("Invalid bot secret")

        # Bot requests carry telegram_id in query params or body
        telegram_id = (
            request.GET.get("telegram_id")
            or request.data.get("telegram_id")
        )

        if telegram_id:
            try:
                telegram_id = int(telegram_id)
            except (ValueError, TypeError):
                raise AuthenticationFailed("Invalid telegram_id")
            request.telegram_id = telegram_id
            return (TelegramUser(telegram_id), None)

        # Bot call without telegram_id (e.g., health check)
        request.telegram_id = None
        return (TelegramUser(0), None)


def get_telegram_id(request) -> int | None:
    """
    Get verified telegram_id from request.

    Returns:
        int: verified telegram_id
        None: if no telegram_id available

    Usage in views:
        telegram_id = get_telegram_id(request)
        if not telegram_id:
            return Response({'error': 'Authentication required'}, status=401)
    """
    return getattr(request, "telegram_id", None)

"""
Telegram authentication middleware.
Extracts telegram_id from Telegram Mini App initData and attaches to request.
"""

import hashlib
import hmac
from urllib.parse import parse_qsl


class TelegramAuthMiddleware:
    """
    Middleware to extract and validate Telegram user data from Mini App.
    The frontend sends initData in X-Telegram-Init-Data header.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Extract telegram_id from header
        init_data = request.META.get('HTTP_X_TELEGRAM_INIT_DATA', '')
        
        if init_data:
            try:
                # Parse initData
                data_dict = dict(parse_qsl(init_data))
                
                # Extract user data
                if 'user' in data_dict:
                    import json
                    user_data = json.loads(data_dict['user'])
                    request.telegram_user_id = user_data.get('id')
                    request.telegram_user = user_data
                else:
                    request.telegram_user_id = None
                    request.telegram_user = None
            except Exception:
                request.telegram_user_id = None
                request.telegram_user = None
        else:
            request.telegram_user_id = None
            request.telegram_user = None

        response = self.get_response(request)
        return response

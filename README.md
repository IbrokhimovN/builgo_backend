# BuildGo Backend

A Django REST Framework backend for a construction materials marketplace with Telegram Mini App integration.

## Overview

BuildGo connects buyers and sellers of construction materials through a Telegram Mini App. The system uses **Telegram-based authentication** (no passwords, no JWT) and supports two user roles:

- **Buyer (Xaridor)**: Browse stores, products, and place orders
- **Seller (Sotuvchi)**: Manage products and orders for their store

## Tech Stack

- **Framework**: Django 5.x + Django REST Framework
- **Database**: PostgreSQL
- **Bot**: python-telegram-bot 22.x
- **Authentication**: Telegram Mini App initData
- **Language**: Python 3.10+

## Project Structure

```
builgo_backend/
├── config/              # Django settings and configuration
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── core/                # Main application
│   ├── models.py       # User, Store, Seller, Product, Order models
│   ├── views.py        # API endpoints
│   ├── serializers.py  # DRF serializers
│   ├── permissions.py  # Custom permissions
│   ├── middleware.py   # Telegram auth middleware
│   ├── admin.py        # Django admin configuration
│   └── urls.py         # URL routing
├── bot/                 # Telegram bot
│   ├── main.py         # Bot entry point
│   └── config.py       # Bot configuration
├── manage.py
├── requirements.txt
└── .env                # Environment variables
```

## Installation

### Prerequisites

- Python 3.10 or higher
- PostgreSQL database
- Telegram Bot token (from [@BotFather](https://t.me/botfather))

### Setup Instructions

1. **Clone the repository** (if applicable)

2. **Create and activate virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   
   Edit `.env` file:
   ```env
   SECRET_KEY=your-secret-key-here
   DEBUG=True
   ALLOWED_HOSTS=*
   
   DB_NAME=buildgo_db
   DB_USER=your_db_user
   DB_PASSWORD=your_db_password
   DB_HOST=localhost
   DB_PORT=5432
   
   TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather
   MINI_APP_URL=https://your_mini_app_url
   BACKEND_URL=http://localhost:8000
   ```

5. **Create PostgreSQL database:**
   ```bash
   createdb buildgo_db
   ```

6. **Run migrations:**
   ```bash
   ./venv/bin/python manage.py migrate
   ```

7. **Create superuser (for admin access):**
   ```bash
   ./venv/bin/python manage.py createsuperuser
   ```

## Running the Application

### Start Django Backend

```bash
./run_server.sh
# Or manually:
./venv/bin/python manage.py runserver
```

The API will be available at: `http://localhost:8000`

### Start Telegram Bot

```bash
./run_bot.sh
# Or manually:
cd bot && ../venv/bin/python main.py
```

## API Endpoints

### Authentication

- `POST /api/telegram-auth/` - Register/update buyer user
- `GET /api/check-seller/?telegram_id=XXX` - Check if user is seller
- `GET /api/seller/me/` - Get seller profile

### Buyer Endpoints

- `GET /api/stores/` - List all active stores
- `GET /api/stores/{id}/categories/` - Get store categories
- `GET /api/stores/{id}/products/` - Get store products
- `GET /api/stores/{id}/products/?category=X` - Filter by category
- `POST /api/orders/` - Create new order
- `GET /api/search/?q=query` - Search products

### Seller Endpoints

- `GET /api/seller/orders/` - List orders for seller's store
- `PATCH /api/seller/orders/{id}/` - Update order status
- `POST /api/seller/products/` - Create new product
- `PATCH /api/seller/products/{id}/` - Update product

## Telegram Bot Usage

### For Buyers

1. Start the bot: `/start`
2. Select "🧱 Xaridor"
3. Provide first name
4. Provide last name
5. Share phone number (via contact button)
6. Bot opens Mini App in buyer mode

### For Sellers

1. Start the bot: `/start`
2. Select "🏪 Sotuvchi"
3. Bot verifies seller status
4. If verified, bot opens Mini App in seller mode
5. If not verified, shows error message

## Admin Panel

Access the Django admin at: `http://localhost:8000/admin/`

You can manage:
- Users
- Stores
- Sellers
- Categories
- Products
- Orders

## Security Features

- ✅ **No JWT tokens** - Authentication via Telegram identity
- ✅ **No passwords** - Users authenticated through Telegram
- ✅ **Store isolation** - Sellers can only access their own store
- ✅ **Automatic store resolution** - Store ID never accepted from frontend
- ✅ **Permission classes** - `IsSeller` and `IsStoreOwner` guards
- ✅ **CORS configured** - Telegram domains whitelisted

## Database Models

- **User**: Telegram-based user (buyer or seller)
- **Store**: Seller's store/shop
- **Seller**: Links user to store
- **Category**: Product categories (per store)
- **Product**: Products with price, unit, availability
- **Order**: Customer orders with status
- **OrderItem**: Individual items in an order

## Development Notes

- All seller APIs automatically resolve the store from `telegram_id`
- Frontend should send `X-Telegram-Init-Data` header with initData
- Order status: `new` → `done`
- Product units: `qop`, `dona`, `kg`, `m`

## Contributing

This is a production-ready backend. Ensure all security practices are maintained when extending functionality.

## License

[Add your license here]
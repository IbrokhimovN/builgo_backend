# BuildGo Backend - API Quick Reference

## Base URL
```
http://localhost:8000
```

## Authentication

Two authentication methods. **Public endpoints** (stores, categories, products, search) require no auth.

### 1. Mini App — Telegram initData (HMAC-SHA256)

All authenticated endpoints from the Mini App must send the raw `initData` string in a header:

```http
X-Telegram-Init-Data: <window.Telegram.WebApp.initData>
```

The backend verifies the HMAC signature using the bot token and extracts `telegram_id` from the verified payload. **`telegram_id` in request body/query is ignored** when this header is present.

### 2. Bot → API — Shared Secret

The Telegram bot authenticates via a shared secret header:

```http
X-Bot-Secret: <BOT_API_SECRET>
```

Bot still passes `telegram_id` in query params or request body — the backend trusts it because the bot is verified by the shared secret.

---

## Public Endpoints (No Auth)

### List Stores
```http
GET /api/stores/
```

**Response (paginated):**
```json
{
  "count": 10,
  "next": "http://localhost:8000/api/stores/?page=2",
  "previous": null,
  "results": [
    {
      "id": 1,
      "name": "Qurilish Materiallari",
      "image": "/media/stores/store1.jpg",
      "is_active": true,
      "created_at": "2026-01-29T21:00:00Z"
    }
  ]
}
```

### Get Store Categories
```http
GET /api/stores/1/categories/
```

**Response (paginated):**
```json
{
  "count": 5,
  "results": [
    {
      "id": 1,
      "name": "Cement",
      "store": 1
    }
  ]
}
```

### Get Store Products
```http
GET /api/stores/1/products/
GET /api/stores/1/products/?category=1
```

**Response (paginated):**
```json
{
  "count": 20,
  "results": [
    {
      "id": 1,
      "store": 1,
      "store_name": "Qurilish Materiallari",
      "category": 1,
      "category_name": "Cement",
      "name": "Cement M400",
      "price": "45000.00",
      "unit": "qop",
      "image": "/media/products/cement.jpg",
      "is_available": true,
      "created_at": "2026-01-29T21:00:00Z"
    }
  ]
}
```

### Search Products
```http
GET /api/search/?q=cement
```

**Response (paginated):**
```json
{
  "count": 3,
  "results": [
    {
      "id": 1,
      "name": "Cement M400",
      "price": "45000.00",
      "store_name": "Qurilish Materiallari",
      "is_available": true,
      ...
    }
  ]
}
```

---

## Customer Endpoints (Bot-Authenticated)

> These endpoints require `X-Bot-Secret` header.

### Create / Update Customer
```http
POST /api/customers/
X-Bot-Secret: <secret>
Content-Type: application/json

{
  "telegram_id": 123456789,
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+998901234567"
}
```

**Response (201 Created / 200 Updated):**
```json
{
  "id": 1,
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+998901234567",
  "created_at": "2026-02-16T12:00:00Z"
}
```

> Note: `telegram_id` is NOT returned in responses (write-only).

### Check Customer Exists
```http
GET /api/customers/check/?telegram_id=123456789
X-Bot-Secret: <secret>
```

**Response:**
```json
{
  "exists": true
}
```

---

## Seller Check (Bot-Authenticated)

### Check Seller Status
```http
GET /api/check-seller/?telegram_id=123456789
X-Bot-Secret: <secret>
```

**Response (is seller):**
```json
{
  "is_seller": true,
  "seller": {
    "id": 1,
    "telegram_id": 123456789,
    "name": "Ali",
    "store": {
      "id": 1,
      "name": "Qurilish Materiallari",
      "image": "/media/stores/store1.jpg",
      "is_active": true,
      "created_at": "2026-01-29T21:00:00Z"
    },
    "is_active": true,
    "created_at": "2026-01-29T21:00:00Z"
  }
}
```

**Response (not seller):**
```json
{
  "is_seller": false
}
```

---

## Order Endpoints (Authenticated)

> Accept both `X-Telegram-Init-Data` (Mini App) and `X-Bot-Secret` (bot).

### Create Order
```http
POST /api/orders/
X-Telegram-Init-Data: <initData>
Content-Type: application/json

{
  "telegram_id": 123456789,
  "store": 1,
  "items": [
    { "product": 1, "quantity": 5 },
    { "product": 2, "quantity": 10 }
  ]
}
```

**Validation:**
- Each product must exist, belong to the specified store, and be available
- Order is created atomically (all-or-nothing)
- `quantity` must be ≥ 1

**Response (201 Created):**
```json
{
  "id": 1,
  "customer": 1,
  "customer_name": "John Doe",
  "store": 1,
  "store_name": "Qurilish Materiallari",
  "status": "new",
  "items": [
    {
      "id": 1,
      "product": 1,
      "product_name": "Cement M400",
      "product_unit": "qop",
      "quantity": 5,
      "price_at_order": "45000.00"
    }
  ],
  "created_at": "2026-01-29T21:00:00Z",
  "updated_at": "2026-01-29T21:00:00Z"
}
```

### My Orders (Customer)
```http
GET /api/orders/my/?telegram_id=123456789
X-Telegram-Init-Data: <initData>
```

**Response (paginated):**
```json
{
  "count": 3,
  "results": [
    {
      "id": 1,
      "customer_name": "John Doe",
      "store_name": "Qurilish Materiallari",
      "status": "new",
      "items": [...],
      "created_at": "2026-01-29T21:00:00Z"
    }
  ]
}
```

---

## Seller Endpoints (Authenticated)

> All seller endpoints require auth. Backend verifies the `telegram_id` belongs to an active seller.

### List Orders (Seller's Store)
```http
GET /api/seller/orders/
X-Telegram-Init-Data: <initData>
```

**Response (paginated):**
```json
{
  "count": 15,
  "results": [
    {
      "id": 1,
      "customer": 5,
      "customer_name": "Customer Name",
      "store": 1,
      "store_name": "My Store",
      "status": "new",
      "items": [...],
      "created_at": "2026-01-29T21:00:00Z"
    }
  ]
}
```

### Update Order Status
```http
PATCH /api/seller/orders/1/
X-Telegram-Init-Data: <initData>
Content-Type: application/json

{
  "status": "processing"
}
```

Valid statuses: `new`, `processing`, `done`, `cancelled`

### Create Product
```http
POST /api/seller/products/
X-Telegram-Init-Data: <initData>
Content-Type: application/json

{
  "category": 1,
  "name": "Cement M500",
  "price": "50000.00",
  "unit": "qop",
  "is_available": true
}
```

> `store` is auto-assigned from seller's profile. DO NOT send store_id.

**Response (201 Created):**
```json
{
  "id": 2,
  "store": 1,
  "store_name": "My Store",
  "category": 1,
  "category_name": "Cement",
  "name": "Cement M500",
  "price": "50000.00",
  "unit": "qop",
  "is_available": true,
  "created_at": "2026-01-29T21:00:00Z"
}
```

### Update Product
```http
PATCH /api/seller/products/2/
X-Telegram-Init-Data: <initData>
Content-Type: application/json

{
  "price": "52000.00",
  "is_available": false
}
```

### Delete Product (Soft-Delete)
```http
DELETE /api/seller/products/2/
X-Telegram-Init-Data: <initData>
```

> Sets `is_available = false` instead of hard delete (preserves order history).

**Response:** `204 No Content`

### List Store Locations
```http
GET /api/seller/locations/
X-Telegram-Init-Data: <initData>
```

### Create Store Location
```http
POST /api/seller/locations/
X-Telegram-Init-Data: <initData>
Content-Type: application/json

{
  "name": "Warehouse",
  "latitude": 41.311081,
  "longitude": 69.240562,
  "address": "Tashkent, Uzbekistan",
  "is_default": true
}
```

### Update Store Location
```http
PATCH /api/seller/locations/1/
X-Telegram-Init-Data: <initData>
Content-Type: application/json

{
  "address": "Updated address"
}
```

### Delete Store Location
```http
DELETE /api/seller/locations/1/
X-Telegram-Init-Data: <initData>
```

**Response:** `204 No Content`

---

## Customer Location Endpoints (Authenticated)

### List My Locations
```http
GET /api/locations/
X-Telegram-Init-Data: <initData>
```

### Create Location
```http
POST /api/locations/
X-Telegram-Init-Data: <initData>
Content-Type: application/json

{
  "name": "Home",
  "latitude": 41.311081,
  "longitude": 69.240562,
  "address": "Tashkent, Uzbekistan",
  "is_default": true
}
```

### Update Location
```http
PATCH /api/locations/1/
X-Telegram-Init-Data: <initData>
Content-Type: application/json

{
  "name": "Office",
  "is_default": false
}
```

### Delete Location
```http
DELETE /api/locations/1/
X-Telegram-Init-Data: <initData>
```

**Response:** `204 No Content`

---

## Testing with cURL

### 1. Browse stores (public — no auth)
```bash
curl http://localhost:8000/api/stores/
curl "http://localhost:8000/api/search/?q=cement"
```

### 2. Check seller (bot auth)
```bash
curl -H "X-Bot-Secret: YOUR_SECRET" \
  "http://localhost:8000/api/check-seller/?telegram_id=123456"
```

### 3. Check customer exists (bot auth)
```bash
curl -H "X-Bot-Secret: YOUR_SECRET" \
  "http://localhost:8000/api/customers/check/?telegram_id=123456"
```

### 4. Create customer (bot auth)
```bash
curl -X POST http://localhost:8000/api/customers/ \
  -H "X-Bot-Secret: YOUR_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"telegram_id": 123456, "first_name": "Test", "last_name": "User", "phone": "+998901234567"}'
```

### 5. Create order (bot or initData auth)
```bash
curl -X POST http://localhost:8000/api/orders/ \
  -H "X-Bot-Secret: YOUR_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"telegram_id": 123456, "store": 1, "items": [{"product": 1, "quantity": 5}]}'
```

---

## Error Responses

### 401 Unauthorized (Missing/Invalid Auth)
```json
{
  "detail": "Invalid initData signature"
}
```

### 400 Bad Request
```json
{
  "error": "telegram_id is required"
}
```

### 403 Forbidden (not a seller)
```json
{
  "error": "Not a seller"
}
```

### 404 Not Found
```json
{
  "error": "Product not found or access denied"
}
```

### 429 Too Many Requests (Rate Limited)
```json
{
  "detail": "Request was throttled. Expected available in 30 seconds."
}
```

---

## Field Enums

### Order Status
- `new` — New order
- `processing` — Being processed
- `done` — Completed
- `cancelled` — Cancelled

### Product Unit
- `qop` — Qop (bag/pack)
- `dona` — Dona (piece)
- `kg` — Kilogram
- `m` — Meter

---

## Pagination

All list endpoints support pagination:
- `?page=1` — First page
- `?page=2` — Second page
- Default page size: **20** items

Response format:
```json
{
  "count": 100,
  "next": "http://localhost:8000/api/endpoint/?page=2",
  "previous": null,
  "results": [...]
}
```

---

## Rate Limiting

- Anonymous requests: **30/minute**
- Exceeding the limit returns `429 Too Many Requests`

---

## Endpoint Summary

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| **Public** | | | |
| GET | `/api/stores/` | None | List active stores |
| GET | `/api/stores/{id}/categories/` | None | Store categories |
| GET | `/api/stores/{id}/products/` | None | Store products |
| GET | `/api/search/?q=` | None | Search products |
| **Bot-Authenticated** | | | |
| POST | `/api/customers/` | Bot Secret | Create/update customer |
| GET | `/api/customers/check/` | Bot Secret | Check customer exists |
| GET | `/api/check-seller/` | Bot Secret | Check seller status |
| **Authenticated (initData or Bot Secret)** | | |
| POST | `/api/orders/` | initData / Bot | Create order |
| GET | `/api/orders/my/` | initData / Bot | Customer order history |
| GET | `/api/locations/` | initData / Bot | List customer locations |
| POST | `/api/locations/` | initData / Bot | Create customer location |
| PATCH | `/api/locations/{id}/` | initData / Bot | Update customer location |
| DELETE | `/api/locations/{id}/` | initData / Bot | Delete customer location |
| GET | `/api/seller/orders/` | initData / Bot | List store orders |
| PATCH | `/api/seller/orders/{id}/` | initData / Bot | Update order status |
| POST | `/api/seller/products/` | initData / Bot | Create product |
| PATCH | `/api/seller/products/{id}/` | initData / Bot | Update product |
| DELETE | `/api/seller/products/{id}/` | initData / Bot | Soft-delete product |
| GET | `/api/seller/locations/` | initData / Bot | List store locations |
| POST | `/api/seller/locations/` | initData / Bot | Create store location |
| PATCH | `/api/seller/locations/{id}/` | initData / Bot | Update store location |
| DELETE | `/api/seller/locations/{id}/` | initData / Bot | Delete store location |

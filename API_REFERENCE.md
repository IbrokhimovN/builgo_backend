# BuildGo Backend - API Quick Reference

## Base URL
```
http://localhost:8000
```

## Authentication

**JWT Bearer Token** — All protected endpoints require `Authorization` header:
```
Authorization: Bearer <access_token>
```

### How to get JWT tokens:
1. Telegram Mini App sends `initData` to `POST /api/telegram-auth/`
2. Backend verifies HMAC-SHA256 and returns `access` + `refresh` tokens
3. Use `access` token in `Authorization: Bearer <token>` header
4. When access token expires, refresh via `POST /api/token/refresh/`

---

## Authentication Endpoints

### Telegram Auth (Login/Register)
```http
POST /api/telegram-auth/
Content-Type: application/json

{
  "init_data": "query_id=AAHdF6IQ...&user=%7B%22id%22%3A123456789...&auth_date=1234567890&hash=abc123..."
}
```

**Response:**
```json
{
  "access": "eyJhbGciOiJIUzI1NiIs...",
  "refresh": "eyJhbGciOiJIUzI1NiIs...",
  "user": {
    "id": 1,
    "telegram_id": 123456789,
    "first_name": "John",
    "last_name": "Doe",
    "phone": "",
    "role": "buyer",
    "date_joined": "2026-01-29T21:00:00Z"
  }
}
```

### Refresh Access Token
```http
POST /api/token/refresh/
Content-Type: application/json

{
  "refresh": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Response:**
```json
{
  "access": "eyJhbGciOiJIUzI1NiIs..."
}
```

### Get My Profile
```http
GET /api/me/
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "id": 1,
  "telegram_id": 123456789,
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+998901234567",
  "role": "buyer",
  "date_joined": "2026-01-29T21:00:00Z"
}
```

### Check Seller Status
```http
GET /api/check-seller/?telegram_id=123456789
```

**Response (is seller):**
```json
{
  "is_seller": true,
  "seller": {
    "id": 1,
    "user": { ... },
    "store": { ... },
    "is_active": true
  }
}
```

**Response (not seller):**
```json
{
  "is_seller": false
}
```

### Get Seller Profile
```http
GET /api/seller/me/
Authorization: Bearer <access_token>
```

### Seller Dashboard
```http
GET /api/seller/dashboard/
Authorization: Bearer <access_token>
```
> ⚠️ Requires `role=seller`. Returns 403 if buyer.

**Response:**
```json
{
  "seller": {
    "id": 1,
    "user": { ... },
    "store": { ... },
    "is_active": true,
    "created_at": "2026-01-29T21:00:00Z"
  },
  "message": "Seller dashboard data"
}
```

---

## Buyer Endpoints

### List Stores
```http
GET /api/stores/
```

**Response:**
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

**Response:**
```json
{
  "count": 5,
  "results": [
    {
      "id": 1,
      "name": "Cement",
      "store": 1
    },
    {
      "id": 2,
      "name": "G'isht",
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

**Response:**
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

### Create Order
```http
POST /api/orders/
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "store": 1,
  "items": [
    {
      "product": 1,
      "quantity": 5
    },
    {
      "product": 2,
      "quantity": 10
    }
  ]
}
```

**Response:**
```json
{
  "id": 1,
  "user": 1,
  "user_name": "John Doe",
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

### Search Products
```http
GET /api/search/?q=cement
```

**Response:**
```json
{
  "results": [
    {
      "id": 1,
      "name": "Cement M400",
      "price": "45000.00",
      "store_name": "Qurilish Materiallari",
      ...
    }
  ]
}
```

---

## Seller Endpoints

> All seller endpoints require `Authorization: Bearer <token>` and `role=seller`.

### List Orders (Seller's Store Only)
```http
GET /api/seller/orders/
Authorization: Bearer <access_token>
```

**Response:**
```json
{
  "count": 10,
  "results": [
    {
      "id": 1,
      "user": 5,
      "user_name": "Customer Name",
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
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "status": "done"
}
```

**Response:**
```json
{
  "id": 1,
  "status": "done",
  ...
}
```

### Create Product
```http
POST /api/seller/products/
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "category": 1,
  "name": "Cement M500",
  "price": "50000.00",
  "unit": "qop",
  "is_available": true
}
```

**Note:** `store` is auto-assigned from seller's profile. DO NOT send store_id.

**Response:**
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
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "price": "52000.00",
  "is_available": false
}
```

**Response:**
```json
{
  "id": 2,
  "name": "Cement M500",
  "price": "52000.00",
  "is_available": false,
  ...
}
```

### List Store Locations
```http
GET /api/seller/locations/
Authorization: Bearer <access_token>
```

**Response:**
```json
[
  {
    "id": 1,
    "name": "Warehouse",
    "latitude": "41.311081",
    "longitude": "69.240562",
    "address": "Tashkent, Uzbekistan",
    "user": null,
    "user_name": null,
    "store": 1,
    "store_name": "My Store",
    "is_default": true,
    "created_at": "2026-02-05T12:00:00Z",
    "updated_at": "2026-02-05T12:00:00Z"
  }
]
```

### Create Store Location
```http
POST /api/seller/locations/
Authorization: Bearer <access_token>
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
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "address": "Updated address"
}
```

### Delete Store Location
```http
DELETE /api/seller/locations/1/
Authorization: Bearer <access_token>
```

---

## Customer Location Endpoints

### List My Locations
```http
GET /api/locations/
Authorization: Bearer <access_token>
```

**Response:**
```json
[
  {
    "id": 1,
    "name": "Home",
    "latitude": "41.311081",
    "longitude": "69.240562",
    "address": "Tashkent, Uzbekistan",
    "user": 1,
    "user_name": "John Doe",
    "store": null,
    "store_name": null,
    "is_default": true,
    "created_at": "2026-02-05T12:00:00Z",
    "updated_at": "2026-02-05T12:00:00Z"
  }
]
```

### Create Location
```http
POST /api/locations/
Authorization: Bearer <access_token>
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
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "name": "Office",
  "is_default": false
}
```

### Delete Location
```http
DELETE /api/locations/1/
Authorization: Bearer <access_token>
```

---

## Testing with cURL

### 1. Login via Telegram initData
```bash
curl -X POST http://localhost:8000/api/telegram-auth/ \
  -H "Content-Type: application/json" \
  -d '{"init_data": "<Telegram initData string>"}'
```

### 2. Use JWT token for protected endpoints
```bash
# Save the access token from step 1
TOKEN="eyJhbGciOiJIUzI1NiIs..."

# Get my profile
curl http://localhost:8000/api/me/ \
  -H "Authorization: Bearer $TOKEN"

# Create an order
curl -X POST http://localhost:8000/api/orders/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"store": 1, "items": [{"product": 1, "quantity": 5}]}'
```

### 3. Test public endpoints (no auth needed)
```bash
curl http://localhost:8000/api/stores/
curl "http://localhost:8000/api/search/?q=cement"
```

---

## Error Responses

### 400 Bad Request
```json
{
  "error": "Invalid data"
}
```

### 401 Unauthorized (no token or invalid/expired token)
```json
{
  "detail": "Given token not valid for any token type",
  "code": "token_not_valid"
}
```

### 403 Forbidden (not a seller)
```json
{
  "detail": "Only sellers can access this endpoint."
}
```

### 404 Not Found
```json
{
  "error": "Product not found or access denied"
}
```

---

## Field Enums

### Order Status
- `new` - New order
- `done` - Completed order

### Product Unit
- `qop` - Qop (bag/pack)
- `dona` - Dona (piece)
- `kg` - Kilogram
- `m` - Meter

### User Role
- `buyer` - Buyer/Customer
- `seller` - Seller

---

## Pagination

All list endpoints support pagination:
- `?page=1` - First page
- `?page=2` - Second page
- Default page size: 20 items

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

## Endpoint Summary

| Method | Endpoint | Auth | Role | Description |
|--------|----------|------|------|-------------|
| POST | `/api/telegram-auth/` | ❌ | — | Login via Telegram initData → JWT |
| POST | `/api/token/refresh/` | ❌ | — | Refresh access token |
| GET | `/api/me/` | ✅ | any | Get my profile |
| GET | `/api/check-seller/` | ❌ | — | Check seller status |
| GET | `/api/stores/` | ❌ | — | List stores |
| GET | `/api/stores/{id}/categories/` | ❌ | — | Store categories |
| GET | `/api/stores/{id}/products/` | ❌ | — | Store products |
| GET | `/api/search/` | ❌ | — | Search products |
| POST | `/api/orders/` | ✅ | any | Create order |
| GET | `/api/locations/` | ✅ | any | List my locations |
| POST | `/api/locations/` | ✅ | any | Create location |
| PATCH | `/api/locations/{id}/` | ✅ | any | Update location |
| DELETE | `/api/locations/{id}/` | ✅ | any | Delete location |
| GET | `/api/seller/dashboard/` | ✅ | seller | Seller dashboard |
| GET | `/api/seller/me/` | ✅ | seller | Seller profile |
| GET | `/api/seller/orders/` | ✅ | seller | List store orders |
| PATCH | `/api/seller/orders/{id}/` | ✅ | seller | Update order status |
| POST | `/api/seller/products/` | ✅ | seller | Create product |
| PATCH | `/api/seller/products/{id}/` | ✅ | seller | Update product |
| GET | `/api/seller/locations/` | ✅ | seller | List store locations |
| POST | `/api/seller/locations/` | ✅ | seller | Create store location |
| PATCH | `/api/seller/locations/{id}/` | ✅ | seller | Update store location |
| DELETE | `/api/seller/locations/{id}/` | ✅ | seller | Delete store location |

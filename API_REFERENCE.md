# BuildGo Backend - API Quick Reference

## Base URL
```
http://localhost:8000
```

## Authentication

All buyer/seller endpoints expect `X-Telegram-Init-Data` header with initData from Telegram Mini App.

---

## Authentication Endpoints

### Register/Update Buyer
```http
POST /api/telegram-auth/
Content-Type: application/json

{
  "telegram_id": 123456789,
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+998901234567"
}
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
  "created_at": "2026-01-29T21:00:00Z"
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
X-Telegram-Init-Data: <initData>
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
X-Telegram-Init-Data: <initData>
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

### List Orders (Seller's Store Only)
```http
GET /api/seller/orders/
X-Telegram-Init-Data: <initData>
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
X-Telegram-Init-Data: <initData>
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

**Note:** `store` is auto-assigned from seller's telegram_id. DO NOT send store_id.

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
X-Telegram-Init-Data: <initData>
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
X-Telegram-Init-Data: <initData>
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

---

## Customer Location Endpoints

### List My Locations
```http
GET /api/locations/
X-Telegram-Init-Data: <initData>
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

---

## Testing with cURL

### Test Buyer Registration
```bash
curl -X POST http://localhost:8000/api/telegram-auth/ \
  -H "Content-Type: application/json" \
  -d '{
    "telegram_id": 123456789,
    "first_name": "Test",
    "last_name": "User",
    "phone": "+998901234567"
  }'
```

### Test Store List
```bash
curl http://localhost:8000/api/stores/
```

### Test Product Search
```bash
curl "http://localhost:8000/api/search/?q=cement"
```

---

## Error Responses

### 400 Bad Request
```json
{
  "error": "Invalid data",
  "details": { ... }
}
```

### 401 Unauthorized
```json
{
  "error": "Telegram authentication required"
}
```

### 403 Forbidden
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

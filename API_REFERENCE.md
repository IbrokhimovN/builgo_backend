# BuildGo Backend - API Quick Reference

## Base URL
```
http://localhost:8000
```

## Authentication

**None.** All endpoints are public. Identity is determined by `telegram_id` parameter.

- **Buyer endpoints**: pass `telegram_id` in request body or query param
- **Seller endpoints**: pass `telegram_id` in request body or query param — backend verifies seller status

---

## Customer Endpoint

### Create / Update Customer
```http
POST /api/customers/
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
  "telegram_id": 123456789,
  "first_name": "John",
  "last_name": "Doe",
  "phone": "+998901234567",
  "created_at": "2026-02-16T12:00:00Z"
}
```

---

## Seller Check

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

> All seller endpoints require `telegram_id` parameter. Backend verifies the telegram_id belongs to an active seller.

### List Orders (Seller's Store Only)
```http
GET /api/seller/orders/?telegram_id=123456789
```

**Response:**
```json
[
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
```

### Update Order Status
```http
PATCH /api/seller/orders/1/
Content-Type: application/json

{
  "telegram_id": 123456789,
  "status": "done"
}
```

### Create Product
```http
POST /api/seller/products/
Content-Type: application/json

{
  "telegram_id": 123456789,
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
Content-Type: application/json

{
  "telegram_id": 123456789,
  "price": "52000.00",
  "is_available": false
}
```

### List Store Locations
```http
GET /api/seller/locations/?telegram_id=123456789
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
    "customer": null,
    "customer_name": null,
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
Content-Type: application/json

{
  "telegram_id": 123456789,
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
Content-Type: application/json

{
  "telegram_id": 123456789,
  "address": "Updated address"
}
```

### Delete Store Location
```http
DELETE /api/seller/locations/1/?telegram_id=123456789
```

---

## Customer Location Endpoints

### List My Locations
```http
GET /api/locations/?telegram_id=123456789
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
    "customer": 1,
    "customer_name": "John Doe",
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
Content-Type: application/json

{
  "telegram_id": 123456789,
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
Content-Type: application/json

{
  "telegram_id": 123456789,
  "name": "Office",
  "is_default": false
}
```

### Delete Location
```http
DELETE /api/locations/1/?telegram_id=123456789
```

---

## Testing with cURL

### 1. Create a customer
```bash
curl -X POST http://localhost:8000/api/customers/ \
  -H "Content-Type: application/json" \
  -d '{"telegram_id": 123456, "first_name": "Test", "last_name": "User", "phone": "+998901234567"}'
```

### 2. Check seller status
```bash
curl "http://localhost:8000/api/check-seller/?telegram_id=123456"
```

### 3. Browse stores and products
```bash
curl http://localhost:8000/api/stores/
curl "http://localhost:8000/api/search/?q=cement"
```

### 4. Create an order
```bash
curl -X POST http://localhost:8000/api/orders/ \
  -H "Content-Type: application/json" \
  -d '{"telegram_id": 123456, "store": 1, "items": [{"product": 1, "quantity": 5}]}'
```

---

## Error Responses

### 400 Bad Request
```json
{ "error": "telegram_id is required" }
```

### 403 Forbidden (not a seller)
```json
{ "error": "Not a seller" }
```

### 404 Not Found
```json
{ "error": "Product not found or access denied" }
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

---

## Pagination

All list endpoints (via `generics.ListAPIView`) support pagination:
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

| Method | Endpoint | Identity | Description |
|--------|----------|----------|-------------|
| POST | `/api/customers/` | body: `telegram_id` | Create/update customer |
| GET | `/api/check-seller/` | query: `telegram_id` | Check seller status |
| GET | `/api/stores/` | — | List stores |
| GET | `/api/stores/{id}/categories/` | — | Store categories |
| GET | `/api/stores/{id}/products/` | — | Store products |
| GET | `/api/search/` | — | Search products |
| POST | `/api/orders/` | body: `telegram_id` | Create order |
| GET | `/api/locations/` | query: `telegram_id` | List customer locations |
| POST | `/api/locations/` | body: `telegram_id` | Create customer location |
| PATCH | `/api/locations/{id}/` | body: `telegram_id` | Update customer location |
| DELETE | `/api/locations/{id}/` | query: `telegram_id` | Delete customer location |
| GET | `/api/seller/orders/` | query: `telegram_id` | List store orders |
| PATCH | `/api/seller/orders/{id}/` | body: `telegram_id` | Update order status |
| POST | `/api/seller/products/` | body: `telegram_id` | Create product |
| PATCH | `/api/seller/products/{id}/` | body: `telegram_id` | Update product |
| GET | `/api/seller/locations/` | query: `telegram_id` | List store locations |
| POST | `/api/seller/locations/` | body: `telegram_id` | Create store location |
| PATCH | `/api/seller/locations/{id}/` | body: `telegram_id` | Update store location |
| DELETE | `/api/seller/locations/{id}/` | query: `telegram_id` | Delete store location |

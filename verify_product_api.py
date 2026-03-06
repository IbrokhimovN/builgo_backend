import sys
import os
import django

sys.path.append('/home/numonjon/python/buildGo/builgo_backend')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from rest_framework.test import APIClient
from core.models import Store, Product, Category, ProductVariant, ProductAttribute, ProductAttributeValue

client = APIClient()

# Create test data
store = Store.objects.first()
category = Category.objects.first()

if not store or not category:
    print("Cannot run test: No store or category found in DB")
    sys.exit(1)

# Delete existing test products if any
Product.objects.filter(name='Test Qizil Gisht').delete()

# Create a new product to test FTS and variants
p = Product.objects.create(
    store=store,
    category=category,
    name='Test Qizil Gisht',
    description='Ajoyib sifatli qizil gisht',
    price='1200',
    quantity=1000,
    unit='dona'
)

# Create attributes and variants
a = ProductAttribute.objects.create(name='Nav')
v_val1 = ProductAttributeValue.objects.create(attribute=a, value='1-nav')
v_val2 = ProductAttributeValue.objects.create(attribute=a, value='2-nav')

v1 = ProductVariant.objects.create(product=p, sku='QG-1', price='1500', quantity=500)
v1.attribute_values.add(v_val1)

v2 = ProductVariant.objects.create(product=p, sku='QG-2', price='1000', quantity=500)
v2.attribute_values.add(v_val2)

print(f"Created Product '{p.name}' with 2 variants.")

# Try searching via API
print("--- Testing Search API ---")
response = client.get('/api/search?q=Qizil')
print(f"Search status code: {response.status_code}")

if response.status_code == 200:
    data = response.json()
    products = data.get('products', [])
    print(f"Products found matching 'Qizil': {len(products)}")
    
    found = False
    for prod in products:
        if prod['id'] == p.id:
            found = True
            print(f"✅ Found our test product: {prod['name']}")
            print(f"   Returned variants: {len(prod.get('variants', []))}")
            if len(prod.get('variants', [])) == 2:
                print("   ✅ Variants serialized correctly")
            else:
                print("   ❌ Variants NOT serialized correctly")
                print(prod)
                
    if not found:
        print("❌ Did NOT find our test product in search results")

print("--- Testing Cart API List ---")
cart_response = client.get('/api/customer/cart/')
print(f"Cart list status code (might be 403 due to no auth): {cart_response.status_code}")

# Clean up
p.delete()
print("Cleaned up test data.")

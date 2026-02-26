import django
import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'builgo_backend.settings'
django.setup()

from core.serializers import ProductCreateSerializer

data = {
    'category': 1,
    'name': 'Test',
    'price': '50000',
    'unit': 'dona',
}

# 1. Test missing quantity
print("Missing quantity:")
ser1 = ProductCreateSerializer(data=data)
ser1.is_valid()
print(ser1.errors)

# 2. Test quantity="undefined"
print("quantity='undefined'")
data['quantity'] = 'undefined'
ser2 = ProductCreateSerializer(data=data)
ser2.is_valid()
print(ser2.errors)

# 3. Test quantity="NaN"
print("quantity='NaN'")
data['quantity'] = 'NaN'
ser3 = ProductCreateSerializer(data=data)
ser3.is_valid()
print(ser3.errors)

# 4. Test quantity="0"
print("quantity='0'")
data['quantity'] = '0'
ser4 = ProductCreateSerializer(data=data)
ser4.is_valid()
print(ser4.errors)

# 5. Test quantity=""
print("quantity=''")
data['quantity'] = ''
ser5 = ProductCreateSerializer(data=data)
ser5.is_valid()
print(ser5.errors)


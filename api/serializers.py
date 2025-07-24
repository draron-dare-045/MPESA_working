# api/serializers.py

from rest_framework import serializers
from .models import User, Animal, Order, OrderItem

# === User and Registration Serializers ===

class UserSerializer(serializers.ModelSerializer):
    """Serializer for displaying user data."""
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'user_type', 'phone_number', 'location']


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer for creating new users. Handles password confirmation."""
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'user_type', 'phone_number', 'location')
        
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


# === Animal Serializer ===

class AnimalSerializer(serializers.ModelSerializer):
    """Serializer for the Animal model."""
    farmer_username = serializers.CharField(source='farmer.username', read_only=True)

    class Meta:
        model = Animal
        fields = [
            'id', 'farmer', 'farmer_username', 'name', 'animal_type', 'breed',
            'age', 'price', 'description', 'image', 
            'is_sold', 'quantity', 'created_at', 'updated_at'
        ]
        read_only_fields = ['farmer', 'is_sold']


# === Order and OrderItem Serializers (Read/Write Pattern) ===

# -- For Reading Order Data --

class OrderItemReadSerializer(serializers.ModelSerializer):
    """Serializer for displaying items within an order."""
    name = serializers.CharField(source='animal.name', read_only=True)
    price = serializers.DecimalField(source='animal.price', max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'animal', 'name', 'price', 'quantity']


class OrderReadSerializer(serializers.ModelSerializer):
    """Serializer for displaying full order details."""
    items = OrderItemReadSerializer(many=True, read_only=True)
    buyer_username = serializers.CharField(source='buyer.username', read_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ['id', 'buyer_username', 'status', 'created_at', 'items', 'total_price']

    def get_total_price(self, order):
        """Calculate the total price of all items in the order."""
        return sum(item.animal.price * item.quantity for item in order.items.all())


# -- For Writing/Creating an Order --

class OrderItemWriteSerializer(serializers.ModelSerializer):
    """Serializer for providing item data when creating an order."""
    class Meta:
        model = OrderItem
        fields = ['animal', 'quantity']


class OrderWriteSerializer(serializers.ModelSerializer):
    """Serializer for creating a new order."""
    items = OrderItemWriteSerializer(many=True)

    class Meta:
        model = Order
        fields = ['id', 'items'] 

    def create(self, validated_data):
        items_data = validated_data.pop('items')
        order = Order.objects.create(**validated_data)

        for item_data in items_data:
            animal = item_data['animal']
            quantity_ordered = item_data['quantity']

            if animal.is_sold or animal.quantity == 0:
                raise serializers.ValidationError(f"'{animal.name}' is out of stock.")
            
            if quantity_ordered > animal.quantity:
                raise serializers.ValidationError(
                    f"Not enough stock for '{animal.name}'. "
                    f"You requested {quantity_ordered}, but only {animal.quantity} are available."
                )
            
            OrderItem.objects.create(order=order, **item_data)

        return order
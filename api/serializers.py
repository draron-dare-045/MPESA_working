from rest_framework import serializers
from .models import User, Animal, Order, OrderItem

# === User and Registration Serializers ===
# These are correct and do not need changes.
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'user_type', 'phone_number', 'location']

class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'user_type', 'phone_number', 'location')
    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user


# === Animal Serializer ===
# This version correctly handles both file uploads and generating the full URL for reading.
class AnimalSerializer(serializers.ModelSerializer):
    """Serializer for the Animal model that handles file uploads and URL generation."""
    farmer_username = serializers.CharField(source='farmer.username', read_only=True)
    image = serializers.ImageField(required=False, use_url=True)

    class Meta:
        model = Animal
        fields = [
            'id', 'farmer', 'farmer_username', 'name', 'animal_type', 'breed',
            'age', 'price', 'description', 'image', 
            'is_sold', 'quantity', 'created_at', 'updated_at'
        ]
        read_only_fields = ['farmer', 'is_sold']

    def to_representation(self, instance):
        """Formats the output to convert the image field to its full URL."""
        representation = super().to_representation(instance)
        if instance.image and hasattr(instance.image, 'url'):
            representation['image'] = instance.image.url
        else:
            representation['image'] = None
        return representation


# === Order and OrderItem Serializers ===
# These are the main serializers for reading and creating orders.
class OrderItemReadSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='animal.name', read_only=True)
    price = serializers.DecimalField(source='animal.price', max_digits=10, decimal_places=2, read_only=True)
    class Meta:
        model = OrderItem
        fields = ['id', 'animal', 'name', 'price', 'quantity']

class OrderReadSerializer(serializers.ModelSerializer):
    items = OrderItemReadSerializer(many=True, read_only=True)
    buyer_username = serializers.CharField(source='buyer.username', read_only=True)
    total_price = serializers.SerializerMethodField()
    class Meta:
        model = Order
        fields = ['id', 'buyer_username', 'status', 'created_at', 'items', 'total_price']
    def get_total_price(self, order):
        return sum(item.animal.price * item.quantity for item in order.items.all())

class OrderItemWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['animal', 'quantity']

class OrderWriteSerializer(serializers.ModelSerializer):
    items = OrderItemWriteSerializer(many=True)

    class Meta:
        model = Order
        # The serializer only needs to validate the 'items' field from the frontend.
        # The 'id' is read-only and the 'buyer' is added by the view.
        fields = ['items']

    def validate_items(self, items):
        """
        Custom validation to check for empty orders.
        """
        if not items:
            raise serializers.ValidationError("Cannot create an empty order. Please add items to your cart.")
        return items


# === THIS IS THE NEW SERIALIZER YOU NEED TO ADD ===
# It is essential for allowing farmers to update the order status.
class OrderStatusUpdateSerializer(serializers.ModelSerializer):
    """
    A dedicated serializer specifically for updating only the status of an Order.
    """
    class Meta:
        model = Order
        fields = ['status']
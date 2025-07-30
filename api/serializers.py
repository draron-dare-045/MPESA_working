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


# === FINAL CORRECTED Animal Serializer ===
# This version correctly handles both file uploads and generating the full URL for reading.

class AnimalSerializer(serializers.ModelSerializer):
    """Serializer for the Animal model that handles file uploads and URL generation."""
    farmer_username = serializers.CharField(source='farmer.username', read_only=True)
    
    # This field will correctly handle the file upload on input (POST/PUT).
    # 'required=False' allows creating/updating an animal without changing the image.
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
        """
        This method formats the output. When reading data (GET), it will convert
        the image field to its full URL from Cloudinary.
        """
        representation = super().to_representation(instance)
        # If the animal instance has an image, replace the default representation with the full URL.
        if instance.image and hasattr(instance.image, 'url'):
            representation['image'] = instance.image.url
        else:
            # If there is no image, ensure the representation is null.
            representation['image'] = None
        return representation


# === Order and OrderItem Serializers (Read/Write Pattern) ===
# These are correct and do not need changes.
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
from rest_framework import viewsets, permissions, status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db import transaction
from . import mpesa_api

from .models import Animal, Order, OrderItem
from .serializers import (
    AnimalSerializer,
    OrderReadSerializer, OrderWriteSerializer,
    UserSerializer,
    UserRegistrationSerializer
)
from .permissions import IsFarmerOrReadOnly, IsOwnerOrAdmin
from . import mpesa_api

User = get_user_model()


class RegisterUserView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]


class UserProfileView(APIView):
    """View to get the profile of the currently logged-in user."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class AnimalViewSet(viewsets.ModelViewSet):
    """ViewSet for listing, creating, retrieving, updating, and deleting Animals."""
    queryset = Animal.objects.filter(is_sold=False).order_by('-created_at')
    serializer_class = AnimalSerializer
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrReadOnly]

    def perform_create(self, serializer):
        """Set the farmer to the currently logged-in user when creating an animal."""
        serializer.save(farmer=self.request.user)


class OrderViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Orders."""
    queryset = Order.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]

    def get_serializer_class(self):
        """Use different serializers for reading vs. writing data."""
        if self.action in ['create', 'update', 'partial_update']:
            return OrderWriteSerializer
        return OrderReadSerializer

    def get_queryset(self):
        """
        Filter orders based on the user's role.
        """
        user = self.request.user
        queryset = super().get_queryset().prefetch_related('items__animal')

        if user.is_staff:
            return queryset
        if user.user_type == User.Types.FARMER:
            return queryset.filter(items__animal__farmer=user).distinct()
        return queryset.filter(buyer=user)

    def perform_create(self, serializer):
        """
        Set the buyer to the currently logged-in user when creating an order.
        """
        if self.request.user.user_type != User.Types.BUYER:
            raise permissions.PermissionDenied("Only Buyers can create orders.")
        serializer.save(buyer=self.request.user, status=Order.OrderStatus.CONFIRMED)


# --- M-Pesa Integration Views ---

class MakePaymentView(APIView):
    """View to initiate an M-Pesa STK push."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        order_id = request.data.get('order_id')
        phone_number = request.data.get('phone_number')

        try:
            order = Order.objects.get(id=order_id, buyer=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found or you are not the owner.'}, status=status.HTTP_404_NOT_FOUND)

        if not phone_number:
            return Response({'error': 'Phone number is required.'}, status=status.HTTP_400_BAD_REQUEST)

        amount = sum(item.animal.price * item.quantity for item in order.items.all())

        # Create the custom transaction description
        item_names = [item.animal.name for item in order.items.all()]
        transaction_desc = ", ".join(item_names)
        if len(transaction_desc) > 90:
            transaction_desc = transaction_desc[:90] + "..."
        
        # --- PROOF FOR YOUR PRESENTATION ---
        # This print statement will show that your code is creating the correct description.
        print(f"Generated Transaction Description: '{transaction_desc}'")
        
        # Call the M-Pesa API function with the real amount and custom description
        response_data = mpesa_api.initiate_stk_push(
            phone_number=phone_number, 
            amount=int(amount),
            order_id=order_id,
            transaction_desc=transaction_desc
        )
        
        if 'errorCode' in response_data:
             return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

        return Response(response_data)

class MpesaCallbackView(APIView):
    """
    Callback view for M-Pesa to send payment status updates.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        # ... (parsing logic remains the same) ...
        order_id = request.data.get('order_id')  # Extract order_id from request data
        
        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(id=order_id)

                if order.status == Order.OrderStatus.CONFIRMED:
                    order.status = Order.OrderStatus.PAID
                    order.save()

                    # --- NEW: Decrement stock quantity ---
                    for item in order.items.all():
                        animal = item.animal
                        # Lock the animal row to prevent race conditions
                        animal_to_update = Animal.objects.select_for_update().get(id=animal.id)
                        
                        if animal_to_update.quantity >= item.quantity:
                            animal_to_update.quantity -= item.quantity
                            if animal_to_update.quantity == 0:
                                animal_to_update.is_sold = True # Mark as out of stock
                            animal_to_update.save()
                        else:
                            # This should be rare due to serializer validation, but is a good safeguard.
                            print(f"CRITICAL ERROR: Stock discrepancy for {animal.name} during payment processing.")
                            
                    
                    print(f"Successfully processed payment and updated stock for Order ID: {order_id}")
                else:
                    print(f"Order ID: {order_id} was already processed or in an invalid state ({order.status}). Ignoring callback.")

        except Order.DoesNotExist:
            print(f"Error: Order with ID {order_id} not found.")
        
        return Response({'status': 'ok'})

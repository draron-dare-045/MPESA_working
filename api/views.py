from rest_framework import viewsets, permissions, status, generics
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers 
from django.db.models import Sum, F, Count
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.utils import timezone
from datetime import timedelta
from django.db.models.functions import TruncDate

from . import mpesa_api
from .models import Animal, Order, OrderItem, User
from .serializers import (
    AnimalSerializer,
    OrderReadSerializer,
    OrderWriteSerializer,
    OrderStatusUpdateSerializer,  # Crucial import
    UserSerializer,
    UserRegistrationSerializer
)
from .permissions import IsFarmerOrReadOnly, IsOrderFarmerOrBuyerOrAdmin


# ------------------- User Registration & Profile Views -------------------
# (These are correct and unchanged)
class RegisterUserView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegistrationSerializer
    permission_classes = [permissions.AllowAny]

class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    @swagger_auto_schema(operation_description="Get profile of logged-in user.", responses={200: UserSerializer()})
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


# ------------------- Animal ViewSet -------------------
# (This is correct and unchanged)
class AnimalViewSet(viewsets.ModelViewSet):
    queryset = Animal.objects.filter(is_sold=False, quantity__gt=0).order_by('-created_at')
    serializer_class = AnimalSerializer
    permission_classes = [permissions.IsAuthenticated, IsFarmerOrReadOnly]
    parser_classes = (MultiPartParser, FormParser)

    def perform_create(self, serializer):
        serializer.save(farmer=self.request.user)


# ------------------- Order ViewSet (FINAL CORRECTED VERSION) -------------------
class OrderViewSet(viewsets.ModelViewSet):
    """ViewSet for managing Orders."""
    queryset = Order.objects.all()
    permission_classes = [permissions.IsAuthenticated, IsOrderFarmerOrBuyerOrAdmin]

    def get_serializer_class(self):
        """Use the correct serializer for the specific action."""
        if self.action == 'create':
            return OrderWriteSerializer
        if self.action in ['update', 'partial_update']:
            return OrderStatusUpdateSerializer
        return OrderReadSerializer

    # --- THIS IS THE UPDATED, HIGH-PERFORMANCE METHOD ---
    def get_queryset(self):
        """
        Efficiently filter and fetch orders for the current user,
        pre-loading all necessary related data to prevent slow performance.
        """
        user = self.request.user
        
        # Start with the base queryset and pre-load all related data.
        # This is the key performance improvement.
        queryset = Order.objects.select_related('buyer').prefetch_related(
            'items__animal'
        ).all()

        if user.is_staff:
            # Admins can see all orders, sorted by most recent
            return queryset.order_by('-created_at')

        if user.user_type == User.Types.FARMER:
            # Farmers see orders containing their animals
            return queryset.filter(items__animal__farmer=user).distinct().order_by('-created_at')
        
        # Buyers see their own orders
        return queryset.filter(buyer=user).order_by('-created_at')

    # --- THIS METHOD IS CORRECT AND UNCHANGED ---
    def perform_create(self, serializer):
        """Set the buyer and reduce stock. The default status (PENDING) is handled by the model."""
        if self.request.user.user_type != User.Types.BUYER:
            raise permissions.PermissionDenied("Only Buyers can create orders.")
        try:
            with transaction.atomic():
                # The model's default='PENDING' is used automatically.
                order = serializer.save(buyer=self.request.user)
                
                items_data = serializer.validated_data.get('items', [])
                for item_data in items_data:
                    animal = item_data['animal']
                    quantity_ordered = item_data['quantity']
                    animal_to_update = Animal.objects.select_for_update().get(id=animal.id)
                    if animal_to_update.quantity < quantity_ordered:
                        raise serializers.ValidationError(f"Not enough stock for '{animal.name}'.")
                    animal_to_update.quantity -= quantity_ordered
                    if animal_to_update.quantity == 0:
                        animal_to_update.is_sold = True
                    animal_to_update.save()
        except Exception as e:
            print(f"Order creation failed: {e}")
            raise serializers.ValidationError("Could not create order due to a stock issue or server error.")
class MakePaymentView(APIView):
    """View to initiate an M-Pesa STK push."""
    permission_classes = [permissions.IsAuthenticated]

    @swagger_auto_schema(
        operation_description="Initiate M-Pesa STK Push for a specific order.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['order_id', 'phone_number'],
            properties={
                'order_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='Order ID'),
                'phone_number': openapi.Schema(type=openapi.TYPE_STRING, description='Phone number in format 2547XXXXXXXX'),
            },
        ),
        responses={200: openapi.Response("STK push initiated")}
    )
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

        item_names = [item.animal.name for item in order.items.all()]
        transaction_desc = ", ".join(item_names)
        if len(transaction_desc) > 90:
            transaction_desc = transaction_desc[:90] + "..."

        print(f"Generated Transaction Description: '{transaction_desc}'")

        response_data = mpesa_api.initiate_stk_push(
            phone_number=phone_number,
            amount=int(amount),
            order_id=order_id,
            transaction_desc=transaction_desc
        )

        if 'errorCode' in response_data:
            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

        return Response(response_data)


# ------------------- M-Pesa Callback -------------------

class MpesaCallbackView(APIView):
    """
    Callback view for M-Pesa to send payment status updates.
    """
    permission_classes = [permissions.AllowAny]

    @swagger_auto_schema(
        operation_description="M-Pesa callback URL to update payment status.",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            required=['order_id'],
            properties={
                'order_id': openapi.Schema(type=openapi.TYPE_INTEGER, description='Order ID from original payment'),
            }
        ),
        responses={200: openapi.Response(description="Callback processed")}
    )
    def post(self, request, *args, **kwargs):
        order_id = request.data.get('order_id')

        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(id=order_id)

                if order.status == Order.OrderStatus.CONFIRMED:
                    order.status = Order.OrderStatus.PAID
                    order.save()

                    for item in order.items.all():
                        animal = item.animal
                        animal_to_update = Animal.objects.select_for_update().get(id=animal.id)

                        if animal_to_update.quantity >= item.quantity:
                            animal_to_update.quantity -= item.quantity
                            if animal_to_update.quantity == 0:
                                animal_to_update.is_sold = True
                            animal_to_update.save()
                        else:
                            print(f"CRITICAL ERROR: Stock discrepancy for {animal.name} during payment processing.")

                    print(f"Successfully processed payment and updated stock for Order ID: {order_id}")
                else:
                    print(f"Order ID: {order_id} was already processed or in an invalid state ({order.status}). Ignoring callback.")

        except Order.DoesNotExist:
            print(f"Error: Order with ID {order_id} not found.")

        return Response({'status': 'ok'})
    

# --- This is your dashboard view, which is correct ---
class FarmerProfessionalDashboardView(APIView):
    """
    Provides all necessary statistics for a professional farmer dashboard.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        if request.user.user_type != User.Types.FARMER:
            return Response({'error': 'Only farmers can access this dashboard.'}, status=status.HTTP_403_FORBIDDEN)

        farmer = request.user
        
        SALES_STATUSES = [Order.OrderStatus.PAID, Order.OrderStatus.CONFIRMED]

        sales_items = OrderItem.objects.filter(animal__farmer=farmer, order__status__in=SALES_STATUSES)
        
        total_revenue = sales_items.aggregate(total=Sum(F('quantity') * F('animal__price')))['total'] or 0
        total_sales_count = Order.objects.filter(items__animal__farmer=farmer, status__in=SALES_STATUSES).distinct().count()
        active_listings_count = Animal.objects.filter(farmer=farmer, is_sold=False, quantity__gt=0).count()

        recent_sales = OrderItem.objects.filter(
            animal__farmer=farmer,
            order__status__in=SALES_STATUSES
        ).select_related('order', 'animal', 'order__buyer').order_by('-order__created_at')[:10]

        recent_sales_data = [{
            'order_id': item.order.id,
            'date': item.order.created_at.strftime('%Y-%m-%d'),
            'animal_name': item.animal.name,
            'quantity': item.quantity,
            'price': item.animal.price,
            'status': item.order.get_status_display(),
            'buyer': item.order.buyer.username
        } for item in recent_sales]

        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        sales_by_day = sales_items.filter(
            order__created_at__gte=thirty_days_ago
        ).annotate(date=TruncDate('order__created_at')) \
         .values('date') \
         .annotate(daily_revenue=Sum(F('quantity') * F('animal__price'))) \
         .order_by('date')
        
        sales_over_time_data = {
            'labels': [item['date'].strftime('%b %d') for item in sales_by_day],
            'data': [item['daily_revenue'] for item in sales_by_day],
        }

        dashboard_data = {
            'total_revenue': total_revenue,
            'total_sales_count': total_sales_count,
            'active_listings_count': active_listings_count,
            'recent_sales': recent_sales_data,
            'sales_over_time': sales_over_time_data,
        }

        return Response(dashboard_data)
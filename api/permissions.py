from rest_framework import permissions

# --- This class is correct, no changes needed ---
class IsFarmerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to only allow farmers to edit objects.
    Read-only access for everyone else.
    """
    def has_permission(self, request, view):
        # Allow read-only access for any request (GET, HEAD, OPTIONS)
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # Write permissions are only allowed to users of type 'FARMER'.
        return request.user.is_authenticated and request.user.user_type == 'FARMER'


# --- This class is for reference, but not used by the OrderViewSet anymore ---
class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admins to edit it.
    """
    def has_object_permission(self, request, view, obj):
        # Admin users can access any object
        if request.user.is_staff:
            return True
        
        # Check if the object has a 'buyer' attribute (like an Order)
        # This is the original logic that was too restrictive.
        if hasattr(obj, 'buyer'):
            return obj.buyer == request.user
            
        # Check if the object has a 'user' attribute
        if hasattr(obj, 'user'):
            return obj.user == request.user
            
        return False


# === THIS IS THE NEW CLASS YOU NEED TO ADD ===
class IsOrderFarmerOrBuyerOrAdmin(permissions.BasePermission):
    """
    Custom permission to allow a user to interact with an order if they are:
    1. The buyer of the order.
    2. A farmer whose animal is included in the order.
    3. An admin/staff user.
    """
    message = "You do not have permission to perform this action on this order."

    def has_object_permission(self, request, view, obj):
        # Admin users can always do everything.
        if request.user.is_staff:
            return True
        
        # The user who bought the order can always access it.
        if obj.buyer == request.user:
            return True
        
        # If the logged-in user is a farmer, we check if any item in the
        # order belongs to them. The .exists() check is very efficient.
        if request.user.user_type == 'FARMER':
            return obj.items.filter(animal__farmer=request.user).exists()

        # For any other case, deny permission.
        return False
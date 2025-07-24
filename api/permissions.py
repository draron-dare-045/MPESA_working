# api/permissions.py

from rest_framework import permissions

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

class IsOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to only allow owners of an object or admins to edit it.
    """
    def has_object_permission(self, request, view, obj):
        # Admin users can access any object
        if request.user.is_staff:
            return True
        
        # Check if the object has a 'buyer' attribute (like an Order)
        if hasattr(obj, 'buyer'):
            return obj.buyer == request.user
            
        # Check if the object has a 'user' attribute
        if hasattr(obj, 'user'):
            return obj.user == request.user
            
        return False

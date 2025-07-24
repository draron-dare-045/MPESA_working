# api/admin.py

from django.contrib import admin
from .models import User, Animal, Order, OrderItem

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0 # Don't show extra empty forms

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'buyer', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    inlines = [OrderItemInline]

admin.site.register(User)
admin.site.register(Animal)
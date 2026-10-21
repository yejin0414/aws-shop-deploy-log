from django.conf import settings

from orders.cart import Cart

from .models import Category


def site(request):
    return {
        "SHOP_NAME": settings.SHOP_NAME,
        "FREE_SHIPPING": settings.FREE_SHIPPING_THRESHOLD,
        "nav_categories": Category.objects.all(),
        "cart_count": Cart(request).count(),
    }

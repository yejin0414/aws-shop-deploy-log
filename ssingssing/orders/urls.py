from django.urls import path

from . import views

app_name = "orders"
urlpatterns = [
    path("cart/", views.cart_view, name="cart"),
    path("cart/add/", views.cart_add, name="cart_add"),
    path("cart/update/", views.cart_update, name="cart_update"),
    path("cart/remove/", views.cart_remove, name="cart_remove"),
    path("checkout/", views.checkout, name="checkout"),
    path("payments/success/", views.payment_success, name="success"),
    path("payments/fail/", views.payment_fail, name="fail"),
    path("orders/", views.order_list, name="list"),
    path("orders/<str:order_id>/", views.order_detail, name="detail"),
    path("orders/<str:order_id>/pay/", views.pay, name="pay"),
    path("orders/<str:order_id>/complete/", views.complete, name="complete"),
    path("orders/<str:order_id>/cancel/", views.order_cancel, name="cancel"),
]

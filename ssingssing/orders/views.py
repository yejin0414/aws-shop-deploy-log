import hashlib
import hmac

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from shop.models import Product

from .cart import Cart
from .forms import CheckoutForm
from .models import Order
from .services import OrderError, cancel_payment, confirm_payment, create_order


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _to_int(value, default=1):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------- 장바구니 ----------------
def cart_view(request):
    cart = Cart(request)
    lines = cart.lines()
    return render(request, "orders/cart.html", {"lines": lines, "summary": cart.summary(lines)})


@require_POST
def cart_add(request):
    product = get_object_or_404(Product, pk=request.POST.get("product_id"), is_active=True)
    qty = max(1, _to_int(request.POST.get("qty"), 1))
    cart = Cart(request)
    in_cart = cart.data.get(str(product.pk), 0)
    if product.sold_out or in_cart + qty > product.stock:
        msg = "품절된 상품이에요." if product.sold_out else f"재고가 {product.stock}개 남았어요."
        if _is_ajax(request):
            return JsonResponse({"ok": False, "message": msg}, status=400)
        messages.error(request, msg)
        return redirect(product.get_absolute_url())
    cart.add(product.pk, qty)
    if request.POST.get("buy_now"):
        return redirect("orders:checkout")
    if _is_ajax(request):
        return JsonResponse({"ok": True, "count": cart.count(), "message": "장바구니에 담았어요"})
    messages.success(request, "장바구니에 담았어요.")
    return redirect(request.POST.get("back") or "orders:cart")


@require_POST
def cart_update(request):
    cart = Cart(request)
    pid = request.POST.get("product_id")
    product = get_object_or_404(Product, pk=pid)
    qty = _to_int(request.POST.get("qty"), 1)
    if qty > product.stock:
        messages.error(request, f"'{product.name}' 재고가 {product.stock}개 남았어요.")
        qty = product.stock
    cart.set(product.pk, qty)
    return redirect("orders:cart")


@require_POST
def cart_remove(request):
    Cart(request).remove(request.POST.get("product_id"))
    messages.info(request, "상품을 장바구니에서 뺐어요.")
    return redirect("orders:cart")


# ---------------- 주문 / 결제 ----------------
@login_required
def checkout(request):
    cart = Cart(request)
    lines = cart.lines()
    if not lines:
        messages.info(request, "장바구니가 비어 있어요.")
        return redirect("orders:cart")

    last = request.user.orders.exclude(recipient="").first()
    initial = {"recipient": request.user.first_name or request.user.username}
    if last:
        initial.update(recipient=last.recipient, phone=last.phone, address=last.address, address_detail=last.address_detail)

    form = CheckoutForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        shipping = {k: data[k] for k in ("recipient", "phone", "address", "address_detail", "memo")}
        try:
            order = create_order(request.user, lines, shipping)
        except OrderError as e:
            messages.error(request, str(e))
            return redirect("orders:cart")
        return redirect("orders:pay", order_id=order.order_id)

    return render(request, "orders/checkout.html", {"form": form, "lines": lines, "summary": cart.summary(lines)})


def _customer_key(user):
    digest = hmac.new(settings.SECRET_KEY.encode(), f"customer-{user.pk}".encode(), hashlib.sha256).hexdigest()
    return f"user-{digest[:32]}"


@login_required
def pay(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    if order.status != Order.PENDING:
        return redirect("orders:detail", order_id=order.order_id)
    return render(request, "orders/pay.html", {
        "order": order,
        "client_key": settings.TOSS_CLIENT_KEY,
        "customer_key": _customer_key(request.user),
        "success_url": request.build_absolute_uri(reverse("orders:success")),
        "fail_url": request.build_absolute_uri(reverse("orders:fail")),
    })


@login_required
def payment_success(request):
    payment_key = request.GET.get("paymentKey", "")
    order_id = request.GET.get("orderId", "")
    amount = _to_int(request.GET.get("amount"), -1)
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    try:
        confirm_payment(order, payment_key, amount)
    except OrderError as e:
        return render(request, "orders/fail.html", {"order": order, "message": str(e)})
    Cart(request).clear()
    return redirect("orders:complete", order_id=order.order_id)


@login_required
def payment_fail(request):
    order = Order.objects.filter(order_id=request.GET.get("orderId", ""), user=request.user).first()
    code = request.GET.get("code", "")
    message = request.GET.get("message", "결제가 완료되지 않았어요.")
    if order and order.status == Order.PENDING and code != "PAY_PROCESS_CANCELED":
        order.status = Order.FAILED
        order.fail_reason = f"{code} {message}"[:200]
        order.save(update_fields=["status", "fail_reason"])
    return render(request, "orders/fail.html", {"order": order, "message": message, "code": code})


@login_required
def complete(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    return render(request, "orders/complete.html", {"order": order})


@login_required
def order_list(request):
    orders = request.user.orders.exclude(status=Order.PENDING).prefetch_related("items")
    return render(request, "orders/order_list.html", {"orders": orders})


@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order.objects.prefetch_related("items"), order_id=order_id, user=request.user)
    return render(request, "orders/order_detail.html", {"order": order})


@login_required
@require_POST
def order_cancel(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    if not order.can_cancel:
        messages.error(request, "배송이 시작된 주문은 취소할 수 없어요. 고객센터로 문의해 주세요.")
    else:
        try:
            cancel_payment(order, "고객 요청 취소")
            messages.success(request, "주문이 취소되고 결제가 환불됐어요.")
        except OrderError as e:
            messages.error(request, f"취소하지 못했어요: {e}")
    return redirect("orders:detail", order_id=order.order_id)

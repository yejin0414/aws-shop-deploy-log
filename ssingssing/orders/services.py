"""주문 생성, 결제 승인, 결제 취소 로직."""
import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from shop.models import Product

from . import toss
from .cart import calc_summary
from .models import Order, OrderItem, PaymentLog

log = logging.getLogger("orders")


class OrderError(Exception):
    pass


@transaction.atomic
def create_order(user, lines, shipping):
    """장바구니 내용으로 '결제대기' 주문을 만듭니다. 금액은 DB 가격으로 다시 계산합니다."""
    if not lines:
        raise OrderError("장바구니가 비어 있어요.")
    for line in lines:
        if line.product.stock < line.quantity:
            raise OrderError(f"'{line.product.name}' 재고가 부족해요. (남은 수량 {line.product.stock}개)")

    s = calc_summary([(l.product.price, l.product.final_price, l.quantity) for l in lines])
    order = Order.objects.create(
        user=user,
        goods_amount=s["goods"],
        discount_amount=s["discount"],
        shipping_fee=s["shipping"],
        total_amount=s["total"],
        **shipping,
    )
    OrderItem.objects.bulk_create([
        OrderItem(order=order, product=l.product, product_name=l.product.name,
                  unit_price=l.product.final_price, quantity=l.quantity)
        for l in lines
    ])
    return order


def confirm_payment(order, payment_key, amount):
    """successUrl로 돌아왔을 때 호출. 금액·재고를 검증한 뒤 토스 승인 API를 부릅니다."""
    if order.status == Order.PAID and order.payment_key == payment_key:
        return order  # 새로고침 등으로 다시 들어온 경우
    if order.status != Order.PENDING:
        raise OrderError("이미 처리된 주문이에요.")
    if amount != order.total_amount:
        _fail(order, "결제 금액이 주문 금액과 다름")
        raise OrderError("결제 금액이 주문 금액과 달라 결제를 진행하지 않았어요.")

    error = None
    toss_error = None
    with transaction.atomic():
        items = list(order.items.all())
        ids = [i.product_id for i in items if i.product_id]
        locked = {p.id: p for p in Product.objects.select_for_update().filter(id__in=ids)}
        for it in items:
            p = locked.get(it.product_id)
            if p is None or not p.is_active or p.stock < it.quantity:
                error = f"'{it.product_name}' 재고가 부족해 결제를 진행하지 않았어요."
                break

        if error is None:
            try:
                status_code, data = toss.confirm(payment_key, order.order_id, amount)
            except toss.TossError as e:
                toss_error = e
                error = e.message

        if error is None:
            PaymentLog.objects.create(order=order, action="CONFIRM", success=True, status_code=status_code, response=data)
            for it in items:
                Product.objects.filter(id=it.product_id).update(stock=F("stock") - it.quantity)
            order.status = Order.PAID
            order.payment_key = payment_key
            order.payment_method = data.get("method", "")
            order.receipt_url = (data.get("receipt") or {}).get("url", "")
            order.paid_at = timezone.now()
            order.fail_reason = ""
            order.save()

    # 실패 기록은 트랜잭션 밖에서 저장해야 롤백되지 않습니다.
    if error is not None:
        if toss_error is not None:
            PaymentLog.objects.create(order=order, action="CONFIRM", success=False,
                                      status_code=toss_error.status_code, response=toss_error.data)
        _fail(order, error)
        raise OrderError(error)

    log.info("결제 승인 %s %s원", order.order_id, amount)
    return order


def cancel_payment(order, reason):
    """결제 취소(전액 환불) 후 재고를 되돌립니다."""
    if order.status == Order.CANCELED:
        return order
    if not order.payment_key or order.status in (Order.PENDING, Order.FAILED):
        raise OrderError("결제가 완료된 주문만 취소할 수 있어요.")
    try:
        status_code, data = toss.cancel(order.payment_key, reason)
    except toss.TossError as e:
        PaymentLog.objects.create(order=order, action="CANCEL", success=False, status_code=e.status_code, response=e.data)
        raise OrderError(e.message)

    with transaction.atomic():
        PaymentLog.objects.create(order=order, action="CANCEL", success=True, status_code=status_code, response=data)
        for it in order.items.all():
            if it.product_id:
                Product.objects.filter(id=it.product_id).update(stock=F("stock") + it.quantity)
        order.status = Order.CANCELED
        order.canceled_at = timezone.now()
        order.fail_reason = reason[:200]
        order.save()
    log.info("결제 취소 %s (%s)", order.order_id, reason)
    return order


def _fail(order, reason):
    order.status = Order.FAILED
    order.fail_reason = reason[:200]
    order.save(update_fields=["status", "fail_reason"])

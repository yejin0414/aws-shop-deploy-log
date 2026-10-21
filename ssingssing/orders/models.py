import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


def new_order_id():
    # 토스 규칙: 6~64자, 영문·숫자·-·_
    return timezone.localtime().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:12]


class Order(models.Model):
    PENDING = "PENDING"
    PAID = "PAID"
    PREPARING = "PREPARING"
    SHIPPING = "SHIPPING"
    DELIVERED = "DELIVERED"
    CANCELED = "CANCELED"
    FAILED = "FAILED"
    STATUS = [
        (PENDING, "결제대기"),
        (PAID, "결제완료"),
        (PREPARING, "상품준비중"),
        (SHIPPING, "배송중"),
        (DELIVERED, "배송완료"),
        (CANCELED, "취소·환불"),
        (FAILED, "결제실패"),
    ]
    CANCELABLE_BY_USER = (PAID, PREPARING)

    order_id = models.CharField("주문번호", max_length=64, unique=True, default=new_order_id, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders", verbose_name="회원")
    status = models.CharField("상태", max_length=12, choices=STATUS, default=PENDING, db_index=True)

    goods_amount = models.PositiveIntegerField("상품금액(할인 후)")
    discount_amount = models.PositiveIntegerField("할인금액", default=0)
    shipping_fee = models.PositiveIntegerField("배송비", default=0)
    total_amount = models.PositiveIntegerField("결제금액")

    recipient = models.CharField("받는 분", max_length=50)
    phone = models.CharField("연락처", max_length=20)
    address = models.CharField("주소", max_length=200)
    address_detail = models.CharField("상세주소", max_length=100, blank=True)
    memo = models.CharField("배송 요청사항", max_length=100, blank=True)

    payment_key = models.CharField("결제키", max_length=200, blank=True)
    payment_method = models.CharField("결제수단", max_length=30, blank=True)
    receipt_url = models.URLField("영수증", max_length=500, blank=True)
    fail_reason = models.CharField("실패·취소 사유", max_length=200, blank=True)

    created_at = models.DateTimeField("주문일시", auto_now_add=True)
    paid_at = models.DateTimeField("결제일시", null=True, blank=True)
    canceled_at = models.DateTimeField("취소일시", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = verbose_name_plural = "주문"

    def __str__(self):
        return self.order_id

    @property
    def order_name(self):
        items = list(self.items.all())
        if not items:
            return "싱싱마켓 주문"
        first = items[0].product_name
        return first if len(items) == 1 else f"{first} 외 {len(items) - 1}건"

    @property
    def can_cancel(self):
        return self.status in self.CANCELABLE_BY_USER and bool(self.payment_key)


class OrderItem(models.Model):
    # 주문 당시의 이름·가격을 그대로 저장 (나중에 가격이 바뀌어도 주문 기록은 유지)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("shop.Product", on_delete=models.SET_NULL, null=True, related_name="+")
    product_name = models.CharField("상품명", max_length=100)
    unit_price = models.PositiveIntegerField("판매가")
    quantity = models.PositiveIntegerField("수량")

    class Meta:
        verbose_name = verbose_name_plural = "주문 상품"

    def __str__(self):
        return f"{self.product_name} x {self.quantity}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class PaymentLog(models.Model):
    """토스 API 호출 기록 (문제 생겼을 때 추적용)."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="logs")
    action = models.CharField(max_length=20)       # CONFIRM / CANCEL
    success = models.BooleanField(default=False)
    status_code = models.PositiveIntegerField(null=True)
    response = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = verbose_name_plural = "결제 로그"

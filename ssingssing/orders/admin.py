from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Order, OrderItem, PaymentLog
from .services import OrderError, cancel_payment


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ("product_name", "unit_price", "quantity", "line_total")
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="합계")
    def line_total(self, obj):
        return f"{obj.line_total:,}원"


class PaymentLogInline(admin.TabularInline):
    model = PaymentLog
    extra = 0
    can_delete = False
    readonly_fields = ("created_at", "action", "success", "status_code", "response")
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


STATUS_COLORS = {
    Order.PENDING: "#6b7280", Order.PAID: "#15803d", Order.PREPARING: "#2563eb",
    Order.SHIPPING: "#7c3aed", Order.DELIVERED: "#111827", Order.CANCELED: "#dc2626", Order.FAILED: "#9ca3af",
}


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_id", "user", "order_name_display", "total_display", "status_badge", "payment_method", "paid_at", "created_at")
    list_filter = ("status", "payment_method", "created_at")
    search_fields = ("order_id", "user__username", "recipient", "phone")
    date_hierarchy = "created_at"
    list_per_page = 30
    inlines = [OrderItemInline, PaymentLogInline]
    readonly_fields = ("order_id", "user", "goods_amount", "discount_amount", "shipping_fee", "total_amount",
                       "payment_key", "payment_method", "receipt_link", "paid_at", "canceled_at", "fail_reason", "created_at")
    fieldsets = (
        ("주문", {"fields": ("order_id", "user", "status", "created_at")}),
        ("금액", {"fields": ("goods_amount", "discount_amount", "shipping_fee", "total_amount")}),
        ("배송지", {"fields": ("recipient", "phone", "address", "address_detail", "memo")}),
        ("결제", {"fields": ("payment_method", "payment_key", "receipt_link", "paid_at", "canceled_at", "fail_reason")}),
    )
    actions = ["mark_preparing", "mark_shipping", "mark_delivered", "refund"]

    @admin.display(description="상품")
    def order_name_display(self, obj):
        return obj.order_name

    @admin.display(description="결제금액", ordering="total_amount")
    def total_display(self, obj):
        return f"{obj.total_amount:,}원"

    @admin.display(description="상태", ordering="status")
    def status_badge(self, obj):
        return format_html('<b style="color:{}">{}</b>', STATUS_COLORS.get(obj.status, "#111"), obj.get_status_display())

    @admin.display(description="영수증")
    def receipt_link(self, obj):
        return format_html('<a href="{}" target="_blank">영수증 보기</a>', obj.receipt_url) if obj.receipt_url else "-"

    def has_delete_permission(self, request, obj=None):
        return False  # 주문 기록은 지우지 않습니다

    def _move(self, request, queryset, allowed_from, to, label):
        changed = queryset.filter(status__in=allowed_from).update(status=to)
        skipped = queryset.count() - changed
        self.message_user(request, f"{changed}건을 '{label}'(으)로 바꿨어요." + (f" ({skipped}건은 상태가 맞지 않아 건너뜀)" if skipped else ""))

    @admin.action(description="상품준비중으로 변경")
    def mark_preparing(self, request, queryset):
        self._move(request, queryset, [Order.PAID], Order.PREPARING, "상품준비중")

    @admin.action(description="배송중으로 변경")
    def mark_shipping(self, request, queryset):
        self._move(request, queryset, [Order.PAID, Order.PREPARING], Order.SHIPPING, "배송중")

    @admin.action(description="배송완료로 변경")
    def mark_delivered(self, request, queryset):
        self._move(request, queryset, [Order.SHIPPING], Order.DELIVERED, "배송완료")

    @admin.action(description="결제 취소(전액 환불)")
    def refund(self, request, queryset):
        ok, fail = 0, []
        for order in queryset:
            try:
                cancel_payment(order, "판매자 취소")
                ok += 1
            except OrderError as e:
                fail.append(f"{order.order_id}: {e}")
        if ok:
            self.message_user(request, f"{ok}건을 환불했어요.")
        for f in fail:
            self.message_user(request, f, level=messages.ERROR)

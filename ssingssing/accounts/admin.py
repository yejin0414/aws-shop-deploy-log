from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from django.db.models import Count, Q, Sum


admin.site.unregister(User)


@admin.register(User)
class MemberAdmin(UserAdmin):
    list_display = ("username", "first_name", "email", "is_active", "is_staff", "paid_orders", "paid_total", "date_joined", "last_login")
    list_filter = ("is_active", "is_staff", "date_joined")
    search_fields = ("username", "first_name", "email")
    actions = ["suspend", "unsuspend"]

    def get_queryset(self, request):
        paid = Q(orders__status__in=["PAID", "PREPARING", "SHIPPING", "DELIVERED"])
        return super().get_queryset(request).annotate(
            _paid_orders=Count("orders", filter=paid),
            _paid_total=Sum("orders__total_amount", filter=paid),
        )

    @admin.display(description="주문 수", ordering="_paid_orders")
    def paid_orders(self, obj):
        return obj._paid_orders

    @admin.display(description="누적 결제", ordering="_paid_total")
    def paid_total(self, obj):
        return f"{obj._paid_total or 0:,}원"

    @admin.action(description="선택 회원 이용 정지")
    def suspend(self, request, queryset):
        n = queryset.filter(is_superuser=False).update(is_active=False)
        self.message_user(request, f"{n}명을 이용 정지했어요. (관리자 계정은 제외)")

    @admin.action(description="선택 회원 정지 해제")
    def unsuspend(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=True)}명의 정지를 해제했어요.")

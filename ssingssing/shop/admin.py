from django.contrib import admin
from django.utils.html import format_html

from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "order", "product_count")
    list_editable = ("order",)

    @admin.display(description="상품 수")
    def product_count(self, obj):
        return obj.products.count()


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("thumb", "name", "category", "price", "sale_price", "final_price_display", "stock", "stock_state", "badge", "is_active")
    list_display_links = ("thumb", "name")
    list_editable = ("price", "sale_price", "stock", "badge", "is_active")
    list_filter = ("is_active", "category", "badge")
    search_fields = ("name", "description")
    list_per_page = 30
    readonly_fields = ("preview", "created_at", "updated_at")
    fieldsets = (
        ("기본 정보", {"fields": ("category", "name", "description", "badge", "is_active")}),
        ("가격·재고", {"fields": ("price", "sale_price", "stock")}),
        ("이미지", {"fields": ("image", "preview")}),
        ("기록", {"fields": ("created_at", "updated_at")}),
    )
    actions = ["activate", "deactivate"]

    @admin.display(description="사진")
    def thumb(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="width:48px;height:48px;object-fit:cover;border-radius:6px">', obj.image.url)
        return "-"

    @admin.display(description="미리보기")
    def preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-width:240px;border-radius:10px">', obj.image.url)
        return "이미지를 올리면 여기에 보여요"

    @admin.display(description="판매가")
    def final_price_display(self, obj):
        return f"{obj.final_price:,}원"

    @admin.display(description="재고 상태")
    def stock_state(self, obj):
        if obj.stock == 0:
            return format_html('<b style="color:#dc2626">품절</b>')
        if obj.stock < 10:
            return format_html('<b style="color:#d97706">부족</b>')
        return "충분"

    @admin.action(description="선택 상품 판매 시작")
    def activate(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=True)}개 상품을 판매 시작했어요.")

    @admin.action(description="선택 상품 판매 중지")
    def deactivate(self, request, queryset):
        self.message_user(request, f"{queryset.update(is_active=False)}개 상품을 판매 중지했어요.")

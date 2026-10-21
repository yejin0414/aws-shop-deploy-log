from django.db import models
from django.urls import reverse


class Category(models.Model):
    name = models.CharField("카테고리명", max_length=50, unique=True)
    order = models.PositiveIntegerField("정렬 순서", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = verbose_name_plural = "카테고리"

    def __str__(self):
        return self.name


class Product(models.Model):
    BADGES = [("", "없음"), ("BEST", "BEST"), ("NEW", "NEW")]

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products", verbose_name="카테고리")
    name = models.CharField("상품명", max_length=100)
    description = models.TextField("설명", blank=True)
    price = models.PositiveIntegerField("정가(원)")
    sale_price = models.PositiveIntegerField("할인가(원)", null=True, blank=True, help_text="비워 두면 정가로 판매")
    stock = models.PositiveIntegerField("재고", default=0)
    image = models.ImageField("이미지", upload_to="products/", blank=True)
    badge = models.CharField("뱃지", max_length=10, choices=BADGES, blank=True)
    is_active = models.BooleanField("판매중", default=True)
    created_at = models.DateTimeField("등록일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = verbose_name_plural = "상품"

    def __str__(self):
        return self.name

    @property
    def final_price(self):
        if self.sale_price and self.sale_price < self.price:
            return self.sale_price
        return self.price

    @property
    def discount_rate(self):
        if self.final_price < self.price:
            return round((1 - self.final_price / self.price) * 100)
        return 0

    @property
    def sold_out(self):
        return self.stock <= 0

    def get_absolute_url(self):
        return reverse("shop:product", args=[self.pk])

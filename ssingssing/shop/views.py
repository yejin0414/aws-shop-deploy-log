from django.db.models import F, Q
from django.shortcuts import get_object_or_404, render

from .models import Category, Product


def home(request):
    products = Product.objects.filter(is_active=True).select_related("category")
    cat_id = request.GET.get("cat")
    q = request.GET.get("q", "").strip()
    sort = request.GET.get("sort", "rec")
    current = None

    if cat_id and cat_id.isdigit():
        current = Category.objects.filter(pk=cat_id).first()
        if current:
            products = products.filter(category=current)
    if q:
        products = products.filter(Q(name__icontains=q) | Q(category__name__icontains=q))
    if sort == "sale":
        products = products.filter(sale_price__isnull=False, sale_price__lt=F("price"))

    products = list(products)
    if sort == "low":
        products.sort(key=lambda p: p.final_price)
    elif sort == "high":
        products.sort(key=lambda p: -p.final_price)

    if q:
        title = f"'{q}' 검색 결과"
    elif sort == "sale":
        title = "오늘의 특가"
    elif current:
        title = current.name
    else:
        title = "오늘의 추천 상품"

    return render(request, "shop/home.html", {
        "products": products, "current": current, "q": q, "sort": sort, "title": title,
        "show_banner": not (q or current or sort == "sale"),
    })


def product_detail(request, pk):
    product = get_object_or_404(Product.objects.select_related("category"), pk=pk, is_active=True)
    related = Product.objects.filter(category=product.category, is_active=True).exclude(pk=pk)[:4]
    return render(request, "shop/product_detail.html", {"product": product, "related": related})

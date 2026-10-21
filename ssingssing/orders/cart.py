"""세션 기반 장바구니. 로그인하지 않아도 담을 수 있고, 주문할 때만 로그인합니다."""
from dataclasses import dataclass

from django.conf import settings

from shop.models import Product

SESSION_KEY = "cart"
MAX_QTY = 99


@dataclass
class Line:
    product: Product
    quantity: int

    @property
    def line_total(self):
        return self.product.final_price * self.quantity

    @property
    def line_original(self):
        return self.product.price * self.quantity


class Cart:
    def __init__(self, request):
        self.session = request.session
        self.data = self.session.get(SESSION_KEY, {})

    def _save(self):
        self.session[SESSION_KEY] = self.data
        self.session.modified = True

    def add(self, product_id, qty=1):
        key = str(product_id)
        self.data[key] = min(MAX_QTY, self.data.get(key, 0) + qty)
        self._save()

    def set(self, product_id, qty):
        key = str(product_id)
        if qty <= 0:
            self.data.pop(key, None)
        else:
            self.data[key] = min(MAX_QTY, qty)
        self._save()

    def remove(self, product_id):
        self.data.pop(str(product_id), None)
        self._save()

    def clear(self):
        self.data = {}
        self._save()

    def lines(self):
        ids = [int(k) for k in self.data]
        products = Product.objects.filter(id__in=ids, is_active=True).select_related("category")
        found = {p.id: p for p in products}
        # 판매 중지된 상품은 장바구니에서 정리
        for pid in ids:
            if pid not in found:
                self.data.pop(str(pid), None)
                self._save()
        return [Line(found[pid], self.data[str(pid)]) for pid in ids if pid in found]

    def count(self):
        return sum(self.data.values())

    def summary(self, lines=None):
        lines = self.lines() if lines is None else lines
        return calc_summary([(l.product.price, l.product.final_price, l.quantity) for l in lines])


def calc_summary(rows):
    """rows: (정가, 판매가, 수량). 결제 금액은 항상 서버에서 이 함수로 계산합니다."""
    original = sum(p * q for p, _, q in rows)
    goods = sum(f * q for _, f, q in rows)
    shipping = 0 if goods == 0 or goods >= settings.FREE_SHIPPING_THRESHOLD else settings.SHIPPING_FEE
    return {
        "original": original,
        "goods": goods,
        "discount": original - goods,
        "shipping": shipping,
        "total": goods + shipping,
        "free_left": max(0, settings.FREE_SHIPPING_THRESHOLD - goods),
        "free_percent": min(100, round(goods / settings.FREE_SHIPPING_THRESHOLD * 100)) if goods else 0,
    }

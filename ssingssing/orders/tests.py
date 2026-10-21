from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from shop.models import Category, Product

from . import toss
from .models import Order


@override_settings(TOSS_SECRET_KEY="test_gsk_dummy", TOSS_CLIENT_KEY="test_gck_dummy")
class ShopFlowTest(TestCase):
    def setUp(self):
        cat = Category.objects.create(name="과일")
        self.apple = Product.objects.create(category=cat, name="사과", price=15900, sale_price=12900, stock=5)
        self.milk = Product.objects.create(category=cat, name="우유", price=3200, stock=10)

    def signup(self):
        res = self.client.post(reverse("accounts:signup"), {
            "username": "buyer1", "first_name": "홍길동", "email": "buyer@example.com",
            "password1": "fresh-market-2026", "password2": "fresh-market-2026",
        })
        self.assertEqual(res.status_code, 302)
        return User.objects.get(username="buyer1")

    def checkout(self):
        return self.client.post(reverse("orders:checkout"), {
            "recipient": "홍길동", "phone": "010-1234-5678", "address": "서울시 종로구 1",
            "memo": "문 앞에 놓아 주세요", "agree": "on",
        })

    def test_signup_password_is_hashed_and_login_logout(self):
        user = self.signup()
        self.assertNotEqual(user.password, "fresh-market-2026")
        self.assertTrue(user.password.startswith("pbkdf2_"))
        self.client.post(reverse("accounts:logout"))
        res = self.client.post(reverse("accounts:login"), {"username": "buyer1", "password": "fresh-market-2026"})
        self.assertEqual(res.status_code, 302)
        self.client.post(reverse("accounts:logout"))
        res = self.client.post(reverse("accounts:login"), {"username": "buyer1", "password": "wrong"})
        self.assertContains(res, "아이디 또는 비밀번호를 확인해 주세요")

    def test_full_purchase_and_refund(self):
        # 비회원으로 담기 → 주문하려면 로그인 필요
        self.client.post(reverse("orders:cart_add"), {"product_id": self.apple.pk, "qty": 2})
        self.client.post(reverse("orders:cart_add"), {"product_id": self.milk.pk, "qty": 1})
        res = self.client.get(reverse("orders:checkout"))
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse("accounts:login"), res.url)

        self.signup()
        res = self.checkout()
        order = Order.objects.get()
        self.assertRedirects(res, reverse("orders:pay", args=[order.order_id]))
        # 12900*2 + 3200 = 29000 → 3만원 미만이라 배송비 3000
        self.assertEqual(order.total_amount, 32000)
        self.assertEqual(order.discount_amount, 6000)

        # 조작된 금액은 승인하지 않음
        with patch.object(toss, "confirm") as m:
            res = self.client.get(reverse("orders:success"), {"paymentKey": "pk_test", "orderId": order.order_id, "amount": 100})
            m.assert_not_called()
        self.assertContains(res, "결제 금액이 주문 금액과 달라")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.FAILED)

        # 새 주문으로 정상 결제
        res = self.checkout()
        order = Order.objects.filter(status=Order.PENDING).get()
        fake = {"method": "카드", "receipt": {"url": "https://example.com/receipt"}}
        with patch.object(toss, "confirm", return_value=(200, fake)) as m:
            res = self.client.get(reverse("orders:success"), {"paymentKey": "pk_test", "orderId": order.order_id, "amount": 32000})
            m.assert_called_once_with("pk_test", order.order_id, 32000)
        self.assertRedirects(res, reverse("orders:complete", args=[order.order_id]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.PAID)
        self.apple.refresh_from_db(); self.milk.refresh_from_db()
        self.assertEqual((self.apple.stock, self.milk.stock), (3, 9))
        self.assertEqual(self.client.session.get("cart"), {})

        # 고객 취소 → 환불, 재고 복구
        with patch.object(toss, "cancel", return_value=(200, {"status": "CANCELED"})) as m:
            self.client.post(reverse("orders:cancel", args=[order.order_id]))
            m.assert_called_once()
        order.refresh_from_db()
        self.assertEqual(order.status, Order.CANCELED)
        self.apple.refresh_from_db()
        self.assertEqual(self.apple.stock, 5)

    def test_toss_rejects_payment(self):
        self.signup()
        self.client.post(reverse("orders:cart_add"), {"product_id": self.apple.pk, "qty": 3})
        self.checkout()
        order = Order.objects.get()
        err = toss.TossError("REJECT_CARD_PAYMENT", "한도초과 혹은 잔액부족으로 결제에 실패했습니다.", 400, {"code": "REJECT_CARD_PAYMENT"})
        with patch.object(toss, "confirm", side_effect=err):
            res = self.client.get(reverse("orders:success"), {"paymentKey": "pk", "orderId": order.order_id, "amount": order.total_amount})
        self.assertContains(res, "한도초과")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.FAILED)
        self.assertEqual(order.logs.filter(success=False).count(), 1)   # 실패 로그가 롤백되지 않고 남음
        self.apple.refresh_from_db()
        self.assertEqual(self.apple.stock, 5)

    def test_out_of_stock(self):
        self.signup()
        res = self.client.post(reverse("orders:cart_add"), {"product_id": self.apple.pk, "qty": 6},
                               HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(res.status_code, 400)

    def test_other_users_order_is_hidden(self):
        self.signup()
        self.client.post(reverse("orders:cart_add"), {"product_id": self.milk.pk})
        self.checkout()
        order = Order.objects.get()
        self.client.post(reverse("accounts:logout"))
        User.objects.create_user("other", password="another-pass-2026")
        self.client.login(username="other", password="another-pass-2026")
        self.assertEqual(self.client.get(reverse("orders:detail", args=[order.order_id])).status_code, 404)

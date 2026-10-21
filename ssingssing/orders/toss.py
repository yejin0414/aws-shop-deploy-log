"""토스페이먼츠 서버 API (결제 승인 / 취소). 시크릿 키는 서버에서만 사용합니다."""
import base64
import uuid

import requests
from django.conf import settings


class TossError(Exception):
    def __init__(self, code, message, status_code=None, data=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.data = data or {}


def _headers():
    token = base64.b64encode(f"{settings.TOSS_SECRET_KEY}:".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "Idempotency-Key": str(uuid.uuid4()),
    }


def _post(path, body):
    try:
        res = requests.post(f"{settings.TOSS_API_BASE}{path}", json=body, headers=_headers(), timeout=30)
    except requests.RequestException as e:
        raise TossError("NETWORK_ERROR", f"결제사 연결에 실패했어요: {e}")
    try:
        data = res.json()
    except ValueError:
        data = {}
    if res.status_code != 200:
        raise TossError(data.get("code", "UNKNOWN"), data.get("message", "결제 처리 중 오류가 발생했어요."), res.status_code, data)
    return res.status_code, data


def confirm(payment_key, order_id, amount):
    return _post("/v1/payments/confirm", {"paymentKey": payment_key, "orderId": order_id, "amount": amount})


def cancel(payment_key, reason):
    return _post(f"/v1/payments/{payment_key}/cancel", {"cancelReason": reason})

import re

from django import forms

MEMOS = [
    ("문 앞에 놓아 주세요", "문 앞에 놓아 주세요"),
    ("경비실에 맡겨 주세요", "경비실에 맡겨 주세요"),
    ("배송 전 연락 주세요", "배송 전 연락 주세요"),
]


class CheckoutForm(forms.Form):
    recipient = forms.CharField(label="받는 분", max_length=50)
    phone = forms.CharField(label="연락처", max_length=20)
    address = forms.CharField(label="주소", max_length=200)
    address_detail = forms.CharField(label="상세 주소", max_length=100, required=False)
    memo = forms.ChoiceField(label="배송 요청사항", choices=MEMOS, required=False)
    agree = forms.BooleanField(label="주문 내용을 확인했으며 결제에 동의합니다", error_messages={"required": "결제 동의에 체크해 주세요."})

    def clean_phone(self):
        phone = re.sub(r"[^0-9]", "", self.cleaned_data["phone"])
        if not re.fullmatch(r"01[0-9]{8,9}", phone):
            raise forms.ValidationError("휴대폰 번호를 확인해 주세요.")
        return f"{phone[:3]}-{phone[3:-4]}-{phone[-4:]}"

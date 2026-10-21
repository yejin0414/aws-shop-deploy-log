from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User


class SignupForm(UserCreationForm):
    email = forms.EmailField(label="이메일", help_text="결제 영수증이 발송될 수 있어요.")
    first_name = forms.CharField(label="이름", max_length=30)

    class Meta:
        model = User
        fields = ("username", "first_name", "email")
        labels = {"username": "아이디"}
        help_texts = {"username": "영문·숫자 4~30자"}

    def clean_username(self):
        username = self.cleaned_data["username"]
        if len(username) < 4:
            raise forms.ValidationError("아이디는 4자 이상이어야 해요.")
        return username

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("이미 가입된 이메일이에요.")
        return email


class LoginForm(AuthenticationForm):
    error_messages = {
        "invalid_login": "아이디 또는 비밀번호를 확인해 주세요.",
        "inactive": "이용이 정지된 계정이에요. 고객센터로 문의해 주세요.",
    }

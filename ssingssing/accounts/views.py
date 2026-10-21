from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import LoginForm, SignupForm


def _safe_next(request, default="shop:home"):
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return nxt
    return default


def signup(request):
    if request.user.is_authenticated:
        return redirect("shop:home")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, f"{user.first_name}님, 가입을 환영해요!")
        return redirect(_safe_next(request))
    return render(request, "accounts/signup.html", {"form": form, "next": request.GET.get("next", "")})


class ShopLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        # 비회원일 때 담은 장바구니 유지
        cart = self.request.session.get("cart", {})
        response = super().form_valid(form)
        if cart:
            self.request.session["cart"] = cart
        return response


@require_POST
def logout_view(request):
    cart = request.session.get("cart", {})
    logout(request)
    if cart:
        request.session["cart"] = cart
    messages.info(request, "로그아웃되었어요.")
    return redirect("shop:home")

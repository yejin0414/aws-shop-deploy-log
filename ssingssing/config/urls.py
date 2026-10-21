from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "싱싱마켓 관리자"
admin.site.site_title = "싱싱마켓 관리자"
admin.site.index_title = "운영 관리"

urlpatterns = [
    path("manage/", admin.site.urls),   # 관리자 주소 (기본 /admin 보다 덜 노출)
    path("accounts/", include("accounts.urls")),
    path("", include("orders.urls")),
    path("", include("shop.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from quotes.views import RememberMeLoginView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", RememberMeLoginView.as_view(), name="login"),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("erp/", include("erp.urls")),
    path("", include("quotes.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

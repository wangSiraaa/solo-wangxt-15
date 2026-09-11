from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("bom.urls")),
    # Vue SPA（frontend_dist 由 vite build 生成；开发期也可用 vite dev server）
    path("", TemplateView.as_view(template_name="index.html"), name="spa"),
]

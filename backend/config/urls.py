from django.conf import settings
from django.contrib import admin
from django.http import Http404, HttpResponse
from django.urls import include, path


def spa_index(request):
    """SPA 入口：直接返回 vite 构建产物，未构建时给出明确指引而非 500。"""
    index_file = settings.BASE_DIR / "frontend_dist" / "index.html"
    if not index_file.exists():
        raise Http404("前端尚未构建：cd frontend && npm install && npm run build")
    return HttpResponse(index_file.read_text(encoding="utf-8"), content_type="text/html; charset=utf-8")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("bom.urls")),
    path("", spa_index, name="spa"),
]

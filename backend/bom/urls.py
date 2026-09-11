from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("materials", views.MaterialViewSet, basename="material")
router.register("products", views.ProductViewSet, basename="product")
router.register("versions", views.BOMVersionViewSet, basename="version")
router.register("lines", views.BOMLineViewSet, basename="line")
router.register("rules", views.SubstituteRuleViewSet, basename="rule")

urlpatterns = [
    path("", include(router.urls)),
    path("compare/", views.compare_versions, name="compare"),
    path("resolve/", views.resolve_serial, name="resolve"),
    path("issue/", views.issue_material, name="issue"),
    path("issues/", views.issue_list, name="issues"),
]

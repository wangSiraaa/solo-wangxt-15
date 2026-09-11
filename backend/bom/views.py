"""
REST 视图：版本比较、发布（环/冲突校验）、替代规则 CRUD、发料与反查。
"""
from django.db import transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .models import BOMLine, BOMVersion, IssueRecord, Material, Product, SubstituteRule
from .serializers import (
    BOMLineSerializer,
    BOMVersionSerializer,
    IssueRecordSerializer,
    MaterialSerializer,
    ProductSerializer,
    SubstituteRuleSerializer,
)
from .services import (
    ResolutionError,
    build_tree,
    diff_versions,
    latest_published,
    snapshot_payload,
    validate_version,
)


class MaterialViewSet(viewsets.ModelViewSet):
    queryset = Material.objects.all()
    serializer_class = MaterialSerializer


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer


class BOMVersionViewSet(viewsets.ModelViewSet):
    serializer_class = BOMVersionSerializer

    def get_queryset(self):
        qs = BOMVersion.objects.select_related("product").annotate(
            line_count=Count("lines", distinct=True),
            rule_count=Count("rules", distinct=True),
        )
        product = self.request.query_params.get("product")
        return qs.filter(product_id=product) if product else qs

    @action(detail=True, methods=["get"])
    def tree(self, request, pk=None):
        """BOM 树（树形展开页面的数据源）。"""
        version = self.get_object()
        return Response(
            {
                "version": BOMVersionSerializer(version).data,
                "tree": build_tree(version),
            }
        )

    @action(detail=True, methods=["get"])
    def validate(self, request, pk=None):
        """发布前预检：替代环 + 区间冲突（含冲突路径）。"""
        return Response(validate_version(self.get_object()))

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """发布版本：替代关系成环或区间冲突指向不同物料时拒绝。"""
        version = self.get_object()
        if version.status == BOMVersion.Status.PUBLISHED:
            return Response({"detail": "版本已发布"}, status=status.HTTP_409_CONFLICT)
        if not version.lines.exists():
            return Response({"detail": "空 BOM 不允许发布"}, status=status.HTTP_400_BAD_REQUEST)

        result = validate_version(version)
        if not result["ok"]:
            return Response(
                {"detail": "校验未通过，禁止发布", **result},
                status=status.HTTP_400_BAD_REQUEST,
            )
        version.status = BOMVersion.Status.PUBLISHED
        version.published_at = timezone.now()
        version.save(update_fields=["status", "published_at"])
        return Response(BOMVersionSerializer(version).data)


@api_view(["GET"])
def compare_versions(request):
    """版本比较：?from=<id>&to=<id> → 树形差异。"""
    from_id, to_id = request.query_params.get("from"), request.query_params.get("to")
    if not from_id or not to_id:
        return Response({"detail": "需要 from 与 to 两个版本 id"}, status=status.HTTP_400_BAD_REQUEST)
    qs = BOMVersion.objects.select_related("product").annotate(
        line_count=Count("lines", distinct=True),
        rule_count=Count("rules", distinct=True),
    )
    v_from = get_object_or_404(qs, pk=from_id)
    v_to = get_object_or_404(qs, pk=to_id)
    result = diff_versions(v_from, v_to)
    return Response(
        {
            "from": BOMVersionSerializer(v_from).data,
            "to": BOMVersionSerializer(v_to).data,
            **result,
        }
    )


class DraftOnlyMixin:
    """清单行与替代规则只允许在草稿版本上改动；发布后快照冻结。"""

    def _check_draft(self, version):
        if version.status != BOMVersion.Status.DRAFT:
            from rest_framework.exceptions import ValidationError

            raise ValidationError("版本已发布，快照只读；如需变更请新建版本")


class BOMLineViewSet(DraftOnlyMixin, viewsets.ModelViewSet):
    serializer_class = BOMLineSerializer

    def get_queryset(self):
        qs = BOMLine.objects.select_related("material", "version")
        version = self.request.query_params.get("version")
        return qs.filter(version_id=version) if version else qs

    def perform_create(self, serializer):
        self._check_draft(serializer.validated_data["version"])
        serializer.save()

    def perform_update(self, serializer):
        self._check_draft(serializer.instance.version)
        serializer.save()

    def perform_destroy(self, instance):
        self._check_draft(instance.version)
        instance.delete()


class SubstituteRuleViewSet(DraftOnlyMixin, viewsets.ModelViewSet):
    serializer_class = SubstituteRuleSerializer

    def get_queryset(self):
        qs = SubstituteRule.objects.select_related("original", "substitute", "version")
        version = self.request.query_params.get("version")
        return qs.filter(version_id=version) if version else qs

    def perform_create(self, serializer):
        self._check_draft(serializer.validated_data["version"])
        serializer.save()

    def perform_update(self, serializer):
        self._check_draft(serializer.instance.version)
        serializer.save()

    def perform_destroy(self, instance):
        self._check_draft(instance.version)
        instance.delete()


@api_view(["GET"])
def resolve_serial(request):
    """反查：?product=<code>&serial=<n> → 该序列号产品应领的物料树。

    已发料 → 返回发料时刻冻结的快照（保持原版本）；
    未发料 → 按最新已发布版本实时解析（新规则只影响未发料产品）。
    """
    code, serial = request.query_params.get("product"), request.query_params.get("serial")
    if not code or not serial:
        return Response({"detail": "需要 product 与 serial 参数"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        serial = int(serial)
        assert serial >= 0
    except (ValueError, AssertionError):
        return Response({"detail": "serial 必须是非负整数"}, status=status.HTTP_400_BAD_REQUEST)

    product = get_object_or_404(Product, code=code)

    issued = (
        IssueRecord.objects.filter(product=product, serial_no=serial)
        .select_related("version")
        .first()
    )
    if issued:
        payload = dict(issued.snapshot)
        payload["issue"] = IssueRecordSerializer(issued).data
        return Response(payload)

    version = latest_published(product)
    if not version:
        return Response({"detail": "该产品没有已发布版本"}, status=status.HTTP_404_NOT_FOUND)
    try:
        return Response(snapshot_payload(product, version, serial, source="live"))
    except ResolutionError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)


@api_view(["POST"])
def issue_material(request):
    """发料：{product, serial_no, operator} → 按当前发布版解析并永久冻结。"""
    code = request.data.get("product")
    serial = request.data.get("serial_no")
    operator = request.data.get("operator", "")
    if code is None or serial is None:
        return Response({"detail": "需要 product 与 serial_no"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        serial = int(serial)
        assert serial >= 0
    except (TypeError, ValueError, AssertionError):
        return Response({"detail": "serial_no 必须是非负整数"}, status=status.HTTP_400_BAD_REQUEST)

    product = get_object_or_404(Product, code=code)
    with transaction.atomic():
        existing = (
            IssueRecord.objects.select_for_update()
            .filter(product=product, serial_no=serial)
            .first()
        )
        if existing:
            return Response(
                {"detail": "该序列号已发料，保持原版本", "issue": IssueRecordSerializer(existing).data},
                status=status.HTTP_409_CONFLICT,
            )
        version = latest_published(product)
        if not version:
            return Response({"detail": "该产品没有已发布版本，无法发料"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            snapshot = snapshot_payload(product, version, serial, source="issued")
        except ResolutionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        record = IssueRecord.objects.create(
            product=product, serial_no=serial, version=version,
            snapshot=snapshot, operator=operator,
        )
    payload = dict(record.snapshot)
    payload["issue"] = IssueRecordSerializer(record).data
    return Response(payload, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def issue_list(request):
    """发料记录列表（可按产品过滤）。"""
    qs = IssueRecord.objects.select_related("product", "version")
    code = request.query_params.get("product")
    if code:
        qs = qs.filter(product__code=code)
    return Response(IssueRecordSerializer(qs[:200], many=True).data)

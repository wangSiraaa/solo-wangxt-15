from rest_framework import serializers

from .models import BOMLine, BOMVersion, IssueRecord, Material, Product, SubstituteRule


class MaterialSerializer(serializers.ModelSerializer):
    class Meta:
        model = Material
        fields = ["id", "code", "name", "spec", "unit"]


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "code", "name"]


class BOMVersionSerializer(serializers.ModelSerializer):
    product_code = serializers.CharField(source="product.code", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    line_count = serializers.IntegerField(read_only=True)
    rule_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = BOMVersion
        fields = [
            "id", "product", "product_code", "product_name", "version",
            "status", "status_display", "note", "created_at", "published_at",
            "line_count", "rule_count",
        ]
        read_only_fields = ["status", "published_at"]


class BOMLineSerializer(serializers.ModelSerializer):
    material_code = serializers.CharField(source="material.code", read_only=True)
    material_name = serializers.CharField(source="material.name", read_only=True)

    class Meta:
        model = BOMLine
        fields = [
            "id", "version", "parent", "material", "material_code",
            "material_name", "quantity", "sort_order",
        ]


class SubstituteRuleSerializer(serializers.ModelSerializer):
    original_code = serializers.CharField(source="original.code", read_only=True)
    original_name = serializers.CharField(source="original.name", read_only=True)
    substitute_code = serializers.CharField(source="substitute.code", read_only=True)
    substitute_name = serializers.CharField(source="substitute.name", read_only=True)

    class Meta:
        model = SubstituteRule
        fields = [
            "id", "version", "original", "original_code", "original_name",
            "substitute", "substitute_code", "substitute_name",
            "serial_start", "serial_end", "note",
        ]

    def validate(self, attrs):
        original = attrs.get("original", getattr(self.instance, "original", None))
        substitute = attrs.get("substitute", getattr(self.instance, "substitute", None))
        start = attrs.get("serial_start", getattr(self.instance, "serial_start", None))
        end = attrs.get("serial_end", getattr(self.instance, "serial_end", None))
        if original and substitute and original == substitute:
            raise serializers.ValidationError("原物料与替代物料不能相同")
        if start is not None and end is not None and end < start:
            raise serializers.ValidationError("截止序列号不能小于起始序列号")
        return attrs


class IssueRecordSerializer(serializers.ModelSerializer):
    product_code = serializers.CharField(source="product.code", read_only=True)
    version_label = serializers.CharField(source="version.version", read_only=True)

    class Meta:
        model = IssueRecord
        fields = [
            "id", "product", "product_code", "serial_no", "version",
            "version_label", "operator", "issued_at", "snapshot",
        ]
        read_only_fields = ["issued_at", "snapshot"]

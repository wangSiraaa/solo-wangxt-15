"""
数据模型：物料、产品、BOM 版本快照、替代料区间规则、发料记录。

设计要点
--------
* BOMVersion + BOMLine 即「清单快照」：每个版本的整棵树完整落库，
  发布后只读，历史版本永远可回溯。
* SubstituteRule 挂在版本上，随版本一起发布；序列号区间为闭区间。
* IssueRecord.snapshot 用 JSONB 冻结发料时刻的解析结果，
  保证「已发料的序列号保持原版本」，新规则只影响未发料产品。
"""
from django.core.exceptions import ValidationError
from django.db import models


class Material(models.Model):
    code = models.CharField("物料编码", max_length=64, unique=True)
    name = models.CharField("物料名称", max_length=128)
    spec = models.CharField("规格", max_length=128, blank=True, default="")
    unit = models.CharField("单位", max_length=16, default="PCS")

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.name}"


class Product(models.Model):
    code = models.CharField("产品编码", max_length=64, unique=True)
    name = models.CharField("产品名称", max_length=128)

    def __str__(self):
        return f"{self.code} {self.name}"


class BOMVersion(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PUBLISHED = "published", "已发布"

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="versions")
    version = models.CharField("版本号", max_length=32)
    status = models.CharField("状态", max_length=16, choices=Status.choices, default=Status.DRAFT)
    note = models.CharField("备注", max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [("product", "version")]
        ordering = ["product_id", "created_at"]

    def __str__(self):
        return f"{self.product.code}@{self.version}({self.get_status_display()})"


class BOMLine(models.Model):
    """BOM 树节点；parent 为空表示产品直接下属的一级件。"""

    version = models.ForeignKey(BOMVersion, on_delete=models.CASCADE, related_name="lines")
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children"
    )
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="bom_lines")
    quantity = models.DecimalField("用量", max_digits=12, decimal_places=4)
    sort_order = models.PositiveIntegerField("同级序号", default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.version} / {self.material.code} x{self.quantity}"


class SubstituteRule(models.Model):
    """替代料区间规则：序列号落在 [serial_start, serial_end] 闭区间时，
    original 可被 substitute 替代（支持多级链式替代）。"""

    version = models.ForeignKey(BOMVersion, on_delete=models.CASCADE, related_name="rules")
    original = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="rules_as_original")
    substitute = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="rules_as_substitute")
    serial_start = models.PositiveIntegerField("起始序列号")
    serial_end = models.PositiveIntegerField("截止序列号")
    note = models.CharField("备注", max_length=255, blank=True, default="")

    class Meta:
        ordering = ["original_id", "serial_start", "id"]

    def clean(self):
        if self.original_id and self.original_id == self.substitute_id:
            raise ValidationError("原物料与替代物料不能相同")
        if self.serial_end is not None and self.serial_start is not None \
                and self.serial_end < self.serial_start:
            raise ValidationError("截止序列号不能小于起始序列号")

    def __str__(self):
        return (
            f"{self.original.code}→{self.substitute.code} "
            f"[{self.serial_start},{self.serial_end}]"
        )


class IssueRecord(models.Model):
    """发料记录：某序列号的产品已按某版本领料，结果永久冻结。"""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="issues")
    serial_no = models.PositiveIntegerField("产品序列号")
    version = models.ForeignKey(BOMVersion, on_delete=models.PROTECT, related_name="issues")
    snapshot = models.JSONField("发料时刻解析快照")
    operator = models.CharField("操作人", max_length=64, blank=True, default="")
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("product", "serial_no")]
        ordering = ["serial_no"]

    def __str__(self):
        return f"{self.product.code}#{self.serial_no} @ {self.version.version}"

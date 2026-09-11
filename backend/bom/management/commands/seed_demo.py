"""
演示数据：python manage.py seed_demo

场景（工业控制器 CTRL-100 的三个 BOM 版本）
-------------------------------------------
V1.0 已发布  —— 原始设计，无替代规则；序列号 1005/1006 已按此版发料（冻结）。
V2.0 草稿    —— 可发布的干净版本，含多级替代规则：
    CAP-100  → CAP-100B   [1000,1999]   一级替代（进口→国产A）
    CAP-100B → CAP-100C   [1500,2500]   二级替代（国产A→国产B加强型）
    IC-OLD   → IC-NEW     [2000,9999]   芯片换代
    ⇒ 边界效果：999→CAP-100；1000~1499→CAP-100B；1500~1999→CAP-100C（链式）；
      2000 起电容回落 CAP-100 且芯片换 IC-NEW。
V3.0 草稿    —— 故意违规，用于演示发布拦截：
    RES-1K→RES-1K-A [1000,2000] 与 RES-1K→RES-1K-B [1500,2500] 区间交叠且指向不同物料；
    IC-OLD→IC-NEW 与 IC-NEW→IC-OLD 构成替代环。

注意：本命令会清空 bom 应用全部数据后重建。
"""
from datetime import datetime, timezone as dt_timezone

from django.core.management.base import BaseCommand
from django.db import transaction

from bom.models import BOMLine, BOMVersion, IssueRecord, Material, Product, SubstituteRule
from bom.services import snapshot_payload


class Command(BaseCommand):
    help = "重建演示数据（清空 bom 应用全部数据）"

    @transaction.atomic
    def handle(self, *args, **options):
        IssueRecord.objects.all().delete()
        SubstituteRule.objects.all().delete()
        BOMLine.objects.all().delete()
        BOMVersion.objects.all().delete()
        Product.objects.all().delete()
        Material.objects.all().delete()

        m = {}

        def mat(code, name, spec=""):
            m[code] = Material.objects.create(code=code, name=name, spec=spec)

        mat("FG-CTRL100", "工业控制器（成品）")
        mat("PWR-01", "电源模块")
        mat("CAP-100", "电解电容 100µF（进口）", "100µF/63V")
        mat("CAP-100B", "电解电容 100µF（国产A）", "100µF/63V")
        mat("CAP-100C", "电解电容 100µF（国产B加强型）", "100µF/80V")
        mat("REC-05", "整流桥堆（插件）")
        mat("REC-06", "整流桥堆（贴片）")
        mat("PCB-MAIN", "主控板")
        mat("IC-OLD", "主控芯片 V1")
        mat("IC-NEW", "主控芯片 V2")
        mat("RES-1K", "贴片电阻 1KΩ", "1KΩ/0603")
        mat("RES-1K-A", "贴片电阻 1KΩ（品牌甲）", "1KΩ/0603")
        mat("RES-1K-B", "贴片电阻 1KΩ（品牌乙）", "1KΩ/0603")
        mat("CASE-AL", "铝合金外壳")
        mat("HEAT-01", "散热片")

        product = Product.objects.create(code="CTRL-100", name="工业控制器")

        def line(version, code, qty, parent=None, order=0):
            return BOMLine.objects.create(
                version=version, parent=parent, material=m[code],
                quantity=qty, sort_order=order,
            )

        # ---------------- V1.0（已发布） ----------------
        v1 = BOMVersion.objects.create(
            product=product, version="V1.0", status=BOMVersion.Status.PUBLISHED,
            note="原始设计", published_at=datetime(2026, 8, 1, 9, 0, tzinfo=dt_timezone.utc),
        )
        pwr = line(v1, "PWR-01", 1, order=1)
        line(v1, "CAP-100", 4, parent=pwr, order=1)
        line(v1, "REC-05", 1, parent=pwr, order=2)
        pcb = line(v1, "PCB-MAIN", 1, order=2)
        line(v1, "IC-OLD", 1, parent=pcb, order=1)
        line(v1, "RES-1K", 10, parent=pcb, order=2)
        line(v1, "CASE-AL", 1, order=3)

        # ---------------- V2.0（草稿，可发布） ----------------
        v2 = BOMVersion.objects.create(
            product=product, version="V2.0", note="电容国产化 + 结构变更（可发布）"
        )
        pwr = line(v2, "PWR-01", 1, order=1)
        line(v2, "CAP-100", 6, parent=pwr, order=1)          # 用量 4→6
        line(v2, "REC-06", 1, parent=pwr, order=2)           # REC-05 换 REC-06
        line(v2, "HEAT-01", 1, parent=pwr, order=3)          # 新增散热片
        pcb = line(v2, "PCB-MAIN", 1, order=2)
        line(v2, "IC-OLD", 1, parent=pcb, order=1)
        line(v2, "RES-1K", 12, parent=pcb, order=2)          # 用量 10→12
        line(v2, "CASE-AL", 1, order=3)

        def rule(version, orig, sub, start, end, note=""):
            return SubstituteRule.objects.create(
                version=version, original=m[orig], substitute=m[sub],
                serial_start=start, serial_end=end, note=note,
            )

        rule(v2, "CAP-100", "CAP-100B", 1000, 1999, "一级替代：进口→国产A")
        rule(v2, "CAP-100B", "CAP-100C", 1500, 2500, "二级替代：国产A→国产B加强型")
        rule(v2, "IC-OLD", "IC-NEW", 2000, 9999, "芯片换代")

        # ---------------- V3.0（草稿，故意违规） ----------------
        v3 = BOMVersion.objects.create(
            product=product, version="V3.0", note="演示用：含区间冲突与替代环，应被发布拦截"
        )
        pwr = line(v3, "PWR-01", 1, order=1)
        line(v3, "CAP-100", 6, parent=pwr, order=1)
        line(v3, "REC-06", 1, parent=pwr, order=2)
        line(v3, "HEAT-01", 1, parent=pwr, order=3)
        pcb = line(v3, "PCB-MAIN", 1, order=2)
        line(v3, "IC-OLD", 1, parent=pcb, order=1)
        line(v3, "RES-1K", 12, parent=pcb, order=2)
        line(v3, "CASE-AL", 1, order=3)
        rule(v3, "RES-1K", "RES-1K-A", 1000, 2000, "品牌甲")
        rule(v3, "RES-1K", "RES-1K-B", 1500, 2500, "品牌乙（与上一规则交叠冲突）")
        rule(v3, "IC-OLD", "IC-NEW", 1000, 9999, "芯片换代")
        rule(v3, "IC-NEW", "IC-OLD", 500, 3000, "回退规则（与上一规则成环）")

        # ---------------- 已发料序列号（冻结在 V1.0） ----------------
        for serial, operator in [(1005, "张工"), (1006, "张工")]:
            IssueRecord.objects.create(
                product=product, serial_no=serial, version=v1,
                snapshot=snapshot_payload(product, v1, serial, source="issued"),
                operator=operator,
            )

        self.stdout.write(self.style.SUCCESS(
            "演示数据就绪：\n"
            "  产品 CTRL-100，版本 V1.0(已发布) / V2.0(草稿·可发布) / V3.0(草稿·含冲突与环)\n"
            "  已发料序列号：1005、1006（冻结在 V1.0）\n"
            "  试试：发布 V2.0 后反查 999 / 1000 / 1499 / 1500 / 1999 / 2000 / 1005"
        ))

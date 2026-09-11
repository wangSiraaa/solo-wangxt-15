"""
业务规则可执行性证明：树形差异、发布拦截（环/冲突）、边界序列号解析、发料冻结。
运行：python manage.py test bom
"""
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APITestCase

from .models import BOMVersion, IssueRecord, Material, Product, SubstituteRule


def find_node(nodes, code):
    """在解析树/差异树中按物料编码找到第一个节点。"""
    for node in nodes:
        key = node.get("original", {}).get("code") or node.get("code")
        if key == code:
            return node
        hit = find_node(node.get("children", []), code)
        if hit:
            return hit
    return None


class WorkbenchTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_demo")
        cls.product = Product.objects.get(code="CTRL-100")
        cls.v1 = BOMVersion.objects.get(version="V1.0")
        cls.v2 = BOMVersion.objects.get(version="V2.0")
        cls.v3 = BOMVersion.objects.get(version="V3.0")

    def publish(self, version):
        return self.client.post(f"/api/versions/{version.id}/publish/")

    def resolve(self, serial):
        return self.client.get(f"/api/resolve/?product=CTRL-100&serial={serial}")


class CompareTests(WorkbenchTestCase):
    def test_tree_diff_added_removed_changed(self):
        resp = self.client.get(f"/api/compare/?from={self.v1.id}&to={self.v2.id}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        tree = resp.data["tree"]

        # 结构差异：REC-05 删除、REC-06/HEAT-01 新增
        self.assertEqual(find_node(tree, "REC-05")["status"], "removed")
        self.assertEqual(find_node(tree, "REC-06")["status"], "added")
        self.assertEqual(find_node(tree, "HEAT-01")["status"], "added")

        # 用量变更：CAP-100 4→6、RES-1K 10→12
        cap = find_node(tree, "CAP-100")
        self.assertEqual(cap["status"], "changed")
        self.assertEqual((cap["quantity_from"], cap["quantity_to"]), ("4", "6"))
        res = find_node(tree, "RES-1K")
        self.assertEqual((res["quantity_from"], res["quantity_to"]), ("10", "12"))

        # 汇总计数与整树一致
        summary = resp.data["summary"]
        self.assertEqual(
            (summary["added"], summary["removed"], summary["changed"]),
            (2, 1, 2),
        )

    def test_compare_requires_both_versions(self):
        resp = self.client.get("/api/compare/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class PublishTests(WorkbenchTestCase):
    def test_publish_clean_version_ok(self):
        resp = self.publish(self.v2)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.v2.refresh_from_db()
        self.assertEqual(self.v2.status, "published")
        self.assertIsNotNone(self.v2.published_at)

    def test_publish_blocked_by_cycle(self):
        resp = self.publish(self.v3)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        cycles = resp.data["cycles"]
        self.assertTrue(cycles, "应检出 IC-OLD↔IC-NEW 替代环")
        flat = "→".join(cycles[0])
        self.assertIn("IC-OLD", flat)
        self.assertIn("IC-NEW", flat)
        self.v3.refresh_from_db()
        self.assertEqual(self.v3.status, "draft", "被拦截的版本不得变成已发布")

    def test_publish_blocked_by_interval_conflict_with_path(self):
        resp = self.publish(self.v3)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        conflicts = resp.data["conflicts"]
        self.assertEqual(len(conflicts), 1)
        c = conflicts[0]
        # 交叠区间 [1500,2000]，指向两种不同物料
        self.assertEqual(c["overlap"], {"serial_start": 1500, "serial_end": 2000})
        targets = {r["substitute"]["code"] for r in c["rules"]}
        self.assertEqual(targets, {"RES-1K-A", "RES-1K-B"})
        # 冲突路径：指出原物料在 BOM 树中的位置
        self.assertIn("PCB-MAIN/RES-1K", c["locations"])

    def test_validate_endpoint_dry_run(self):
        resp = self.client.get(f"/api/versions/{self.v3.id}/validate/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["ok"])
        self.assertTrue(resp.data["cycles"])
        self.assertTrue(resp.data["conflicts"])

    def test_double_publish_rejected(self):
        self.assertEqual(self.publish(self.v2).status_code, 200)
        self.assertEqual(self.publish(self.v2).status_code, status.HTTP_409_CONFLICT)


class BoundaryResolutionTests(WorkbenchTestCase):
    """多级替代 + 边界序列号：CAP-100→CAP-100B [1000,1999]，CAP-100B→CAP-100C [1500,2500]。"""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.v2.status = "published"
        from django.utils import timezone

        cls.v2.published_at = timezone.now()
        cls.v2.save(update_fields=["status", "published_at"])

    def effective_code(self, serial, code="CAP-100"):
        resp = self.resolve(serial)
        self.assertEqual(resp.status_code, 200, resp.content)
        node = find_node(resp.data["lines"], code)
        self.assertIsNotNone(node, f"序列号 {serial} 的解析树中应包含 {code}")
        return node

    def test_serial_999_below_range_keeps_original(self):
        node = self.effective_code(999)
        self.assertEqual(node["effective"]["code"], "CAP-100")
        self.assertFalse(node["substituted"])

    def test_serial_1000_range_start_first_hop(self):
        node = self.effective_code(1000)
        self.assertEqual(node["effective"]["code"], "CAP-100B")
        self.assertEqual(len(node["chain"]), 1)

    def test_serial_1499_still_first_hop(self):
        self.assertEqual(self.effective_code(1499)["effective"]["code"], "CAP-100B")

    def test_serial_1500_chain_reaches_second_hop(self):
        node = self.effective_code(1500)
        self.assertEqual(node["effective"]["code"], "CAP-100C")
        hops = [(h["from"]["code"], h["to"]["code"]) for h in node["chain"]]
        self.assertEqual(hops, [("CAP-100", "CAP-100B"), ("CAP-100B", "CAP-100C")])

    def test_serial_1999_range_end_still_chained(self):
        self.assertEqual(self.effective_code(1999)["effective"]["code"], "CAP-100C")

    def test_serial_2000_first_rule_expired_falls_back(self):
        node = self.effective_code(2000)
        self.assertEqual(node["effective"]["code"], "CAP-100")
        # 同序列号下芯片规则生效：IC-OLD→IC-NEW [2000,9999]
        ic = self.effective_code(2000, "IC-OLD")
        self.assertEqual(ic["effective"]["code"], "IC-NEW")

    def test_serial_1999_chip_not_yet_substituted(self):
        self.assertEqual(self.effective_code(1999, "IC-OLD")["effective"]["code"], "IC-OLD")


class IssueFreezeTests(WorkbenchTestCase):
    def test_issued_serial_keeps_original_version(self):
        # 1005 在 V1.0 时期已发料；发布 V2.0 后仍返回 V1.0 快照
        self.publish(self.v2)
        resp = self.resolve(1005)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["source"], "issued")
        self.assertEqual(resp.data["version"]["version"], "V1.0")
        cap = find_node(resp.data["lines"], "CAP-100")
        self.assertEqual(cap["quantity"], "4")  # V1.0 用量，而非 V2.0 的 6
        self.assertFalse(cap["substituted"])    # 新替代规则不影响已发料产品
        self.assertIsNotNone(find_node(resp.data["lines"], "REC-05"))  # 旧件仍在
        self.assertIsNone(find_node(resp.data["lines"], "HEAT-01"))    # 新件不出现

    def test_unissued_serial_uses_new_rules(self):
        self.publish(self.v2)
        resp = self.resolve(1600)
        self.assertEqual(resp.data["source"], "live")
        self.assertEqual(resp.data["version"]["version"], "V2.0")
        self.assertEqual(find_node(resp.data["lines"], "CAP-100")["effective"]["code"], "CAP-100C")

    def test_issue_freezes_snapshot_and_is_idempotent(self):
        self.publish(self.v2)
        payload = {"product": "CTRL-100", "serial_no": 1500, "operator": "李工"}
        first = self.client.post("/api/issue/", payload, format="json")
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(first.data["source"], "issued")
        self.assertEqual(
            find_node(first.data["lines"], "CAP-100")["effective"]["code"], "CAP-100C"
        )
        # 重复发料 → 409，且快照不被覆盖
        second = self.client.post("/api/issue/", payload, format="json")
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(IssueRecord.objects.filter(serial_no=1500).count(), 1)
        # 之后再查，走冻结快照
        again = self.resolve(1500)
        self.assertEqual(again.data["source"], "issued")

    def test_issue_without_published_version_fails(self):
        product = Product.objects.create(code="NEW-1", name="无版本产品")
        resp = self.client.post(
            "/api/issue/", {"product": product.code, "serial_no": 1}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class DraftFreezeTests(WorkbenchTestCase):
    def test_rules_readonly_after_publish(self):
        self.publish(self.v2)
        rule = self.v2.rules.first()
        resp = self.client.delete(f"/api/rules/{rule.id}/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        resp = self.client.post(
            "/api/rules/",
            {
                "version": self.v2.id,
                "original": Material.objects.get(code="CAP-100").id,
                "substitute": Material.objects.get(code="CAP-100C").id,
                "serial_start": 1,
                "serial_end": 10,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_rule_field_validation(self):
        cap = Material.objects.get(code="CAP-100")
        # 区间倒置
        resp = self.client.post(
            "/api/rules/",
            {"version": self.v2.id, "original": cap.id,
             "substitute": Material.objects.get(code="CAP-100B").id,
             "serial_start": 2000, "serial_end": 1000},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        # 自我替代
        resp = self.client.post(
            "/api/rules/",
            {"version": self.v2.id, "original": cap.id, "substitute": cap.id,
             "serial_start": 1, "serial_end": 10},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SubstituteRule.objects.filter(version=self.v2).count(), 3)

"""
真实浏览器 E2E 验证：版本比较 → 发布 → 冲突拦截 → 发料反查 → 冻结。
运行：LD_LIBRARY_PATH=... python e2e/verify.py
前置：后端 runserver :8000 已启动且已 seed_demo。
"""
import pathlib
import sys

from playwright.sync_api import expect, sync_playwright

BASE = "http://127.0.0.1:8000"
SHOTS = pathlib.Path(__file__).parent / "shots"
SHOTS.mkdir(exist_ok=True)

passed = []


def ok(name):
    passed.append(name)
    print(f"  ✓ {name}")


def run(page):
    # ---------- 1. 首页 ----------
    page.goto(BASE + "/")
    expect(page.get_by_role("heading", name="产品 BOM 版本")).to_be_visible()
    for v in ("V1.0", "V2.0", "V3.0"):
        expect(page.get_by_role("cell", name=v, exact=True)).to_be_visible()
    ok("首页加载，三个版本在列表中")
    page.screenshot(path=str(SHOTS / "1-home.png"), full_page=True)

    # ---------- 2. 版本比较：树形差异 + 展开/收起 ----------
    page.get_by_role("link", name="版本比较").click()
    expect(page.locator(".chip.added")).to_have_text("新增 2")
    expect(page.locator(".chip.removed")).to_have_text("删除 1")
    expect(page.locator(".chip.changed")).to_have_text("变更 2")
    expect(page.locator(".trow.added .code", has_text="REC-06").first).to_be_visible()
    expect(page.locator(".trow.removed .code", has_text="REC-05").first).to_be_visible()
    cap_row = page.locator(".trow.changed", has_text="CAP-100").first
    expect(cap_row).to_contain_text("4")
    expect(cap_row).to_contain_text("6")
    ok("版本比较：新增/删除/变更统计与树节点高亮正确")

    pwr_caret = page.locator(".trow", has_text="PWR-01").first.locator(".caret")
    heat = page.locator(".trow .code", has_text="HEAT-01")
    expect(heat).to_be_visible()
    pwr_caret.click()  # 收起 PWR-01 子树
    expect(heat).to_be_hidden()
    pwr_caret.click()  # 再展开
    expect(heat).to_be_visible()
    ok("树形展开/收起交互正常")
    page.screenshot(path=str(SHOTS / "2-compare.png"), full_page=True)

    # ---------- 3. V2.0：校验通过 → 发布 ----------
    page.get_by_role("link", name="版本总览").click()
    page.locator("tr", has_text="V2.0").get_by_role("button", name="打开").click()
    expect(page.get_by_text("✓ 无替代环、无区间冲突，可以发布")).to_be_visible()
    expect(page.get_by_text("CAP-100B", exact=True).first).to_be_visible()
    ok("V2.0 详情：BOM 树 + 多级替代规则展示，预检通过")
    page.get_by_role("button", name="发布版本").click()
    expect(page.get_by_text("发布成功")).to_be_visible()
    expect(page.locator(".badge.published").first).to_be_visible()
    ok("V2.0 发布成功，状态变为已发布")
    page.screenshot(path=str(SHOTS / "3-publish-v2.png"), full_page=True)

    # ---------- 4. V3.0：环 + 区间冲突 → 禁止发布 ----------
    page.get_by_role("link", name="版本总览").click()
    page.locator("tr", has_text="V3.0").get_by_role("button", name="打开").click()
    expect(page.get_by_text("替代环 1")).to_be_visible()
    expect(page.locator(".cycle-item")).to_contain_text("IC-OLD → IC-NEW → IC-OLD")
    expect(page.get_by_text("区间冲突 1")).to_be_visible()
    conflict = page.locator(".conflict-item").first
    expect(conflict).to_contain_text("[1500, 2000]")
    expect(conflict).to_contain_text("RES-1K-A")
    expect(conflict).to_contain_text("RES-1K-B")
    expect(conflict.locator(".loc")).to_have_text("PCB-MAIN/RES-1K")
    expect(page.get_by_role("button", name="发布版本")).to_be_disabled()
    ok("V3.0：替代环与区间冲突（含冲突路径 PCB-MAIN/RES-1K）展示，发布按钮禁用")
    page.screenshot(path=str(SHOTS / "4-v3-blocked.png"), full_page=True)

    # ---------- 5. 发料反查：边界序列号 ----------
    page.get_by_role("link", name="发料反查").click()
    page.get_by_placeholder("如 1500").fill("1500")
    page.get_by_role("button", name="查询").click()
    expect(page.locator(".badge.live")).to_be_visible()
    cap = page.locator(".trow.substituted", has_text="CAP-100").first
    expect(cap).to_contain_text("CAP-100C")
    expect(cap.locator(".hop").first).to_contain_text("CAP-100→CAP-100B [1000-1999]")
    expect(cap.locator(".hop").nth(1)).to_contain_text("CAP-100B→CAP-100C [1500-2500]")
    ok("序列号 1500：两级替代链 CAP-100→CAP-100B→CAP-100C 展示正确")

    page.get_by_placeholder("如 1500").fill("999")
    page.get_by_role("button", name="查询").click()
    expect(page.locator(".badge.live")).to_be_visible()
    expect(page.locator(".trow.substituted")).to_have_count(0)
    ok("序列号 999：区间外，无替代，领原物料")

    # ---------- 6. 发料冻结 ----------
    page.get_by_placeholder("如 1500").fill("1500")
    page.get_by_role("button", name="查询").click()
    page.get_by_role("button", name="按此结果发料（冻结）").click()
    expect(page.locator(".badge.issued")).to_be_visible()
    expect(page.get_by_text("该序列号已发料，保持原版本结果")).to_be_visible()
    ok("1500 发料成功，结果冻结为快照")

    page.get_by_placeholder("如 1500").fill("1005")
    page.get_by_role("button", name="查询").click()
    expect(page.locator(".badge.issued")).to_be_visible()
    expect(page.locator(".summary-chips")).to_contain_text("版本 V1.0")
    expect(page.locator(".trow", has_text="REC-05").first).to_be_visible()
    expect(page.locator(".trow .code", has_text="HEAT-01")).to_have_count(0)
    ok("1005 已发料：V2.0 发布后仍保持 V1.0 快照（REC-05 在、HEAT-01 无）")
    page.screenshot(path=str(SHOTS / "5-resolve.png"), full_page=True)


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1360, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        run(page)
    finally:
        browser.close()
    if errors:
        print("页面 JS 错误:", errors)
        sys.exit(1)

print(f"\n全部通过：{len(passed)} 项浏览器验证")

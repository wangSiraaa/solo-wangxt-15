# 变更工作台 · 替代料生效边界管理

工程师比较两版物料清单（树形差异），质量人员限定替代料适用的序列号区间，
生产人员按序列号反查应领物料。Vue 3 + Django REST Framework + PostgreSQL。

## 目录结构

```
backend/            Django 项目（config）+ 业务应用（bom）
  bom/services.py   规则引擎：树构建 / 版本比较 / 环检测 / 区间冲突 / 序列号解析
  bom/tests.py      20 个业务规则测试
  frontend_dist/    vite 构建产物（index.html + assets），由 Django 提供
frontend/           Vue 3 + vite 源码（版本总览 / 版本比较 / 版本详情·发布 / 发料反查）
e2e/verify.py       Playwright 真实浏览器验证（10 项）
```

## 启动

```bash
# 1. PostgreSQL（仓库内嵌 16.4，免 root；也可设 PGHOST 等环境变量用外部实例）
/workspace/.pgsql/bin/pg_ctl -D /workspace/.pgdata \
    -o "-k /tmp/.pgsock -p 5432 -c listen_addresses='127.0.0.1'" \
    -l /workspace/.pgdata.log -w start

# 2. 后端（.venv 已装好依赖；新环境则 pip install django djangorestframework "psycopg[binary]" django-cors-headers）
cd backend
/workspace/.venv/bin/python manage.py migrate
/workspace/.venv/bin/python manage.py seed_demo     # 演示数据（会清空 bom 应用数据）
/workspace/.venv/bin/python manage.py runserver 0.0.0.0:8000

# 3. 前端（已构建到 backend/frontend_dist；改动源码后重新构建）
cd frontend && npm install && npm run build
```

访问 http://127.0.0.1:8000/ （SPA 入口），API 在 `/api/` 下。
前端开发热更新：`cd frontend && npm run dev`（vite :5173 代理 /api 到 :8000）。

## 业务规则

| 规则 | 实现 | 验证 |
|---|---|---|
| 替代关系成环 → 禁止发布 | `services.find_cycles` DFS 找环，发布接口 400 返回环路径 | V3.0：`IC-OLD → IC-NEW → IC-OLD` |
| 区间交叠且指向不同物料 → 指出冲突路径 | `services.find_conflicts` 同原物料两两扫区间，返回交叠段+两条规则+BOM 位置 | V3.0：`RES-1K` 在 `[1500,2000]` 同时指向 `RES-1K-A/B`，路径 `PCB-MAIN/RES-1K` |
| 已发料序列号保持原版本 | `IssueRecord.snapshot` JSONB 冻结，反查优先命中 | 1005/1006 永远返回 V1.0 结果 |
| 新规则只影响未发料产品 | 未发料按最新已发布版本实时解析 | 发料 1500 后改规则不影响 1500 |
| 发布后快照只读 | 清单行/规则写操作校验 `status == draft` | 测试 `DraftFreezeTests` |

## 演示数据（seed_demo）

- **V1.0 已发布**：原始设计；序列号 1005、1006 已按此版发料。
- **V2.0 草稿·可发布**：多级替代
  `CAP-100→CAP-100B [1000,1999]`、`CAP-100B→CAP-100C [1500,2500]`、`IC-OLD→IC-NEW [2000,9999]`
- **V3.0 草稿·违规**：区间冲突 + 替代环，用于演示发布拦截。

边界序列号（发布 V2.0 后在「发料反查」验证）：

| 序列号 | 电容行结果 | 说明 |
|---|---|---|
| 999 | CAP-100 | 区间外，领原物料 |
| 1000 / 1499 | CAP-100B | 一级替代 |
| 1500 / 1999 | CAP-100C | 两级链式替代 |
| 2000 | CAP-100 + IC-NEW | 首条规则失效回落，芯片规则生效 |
| 1005 | V1.0 快照 | 已发料，冻结 |

## 测试

```bash
cd backend
/workspace/.venv/bin/python manage.py test bom        # 20 个业务规则测试
LD_LIBRARY_PATH=/workspace/.syslibs/usr/lib/aarch64-linux-gnu:/workspace/.syslibs/lib/aarch64-linux-gnu \
  /workspace/.venv/bin/python /workspace/e2e/verify.py  # 10 项真实浏览器验证（需 runserver 已启动）
```

## API 一览

```
GET  /api/versions/                     版本列表
GET  /api/versions/{id}/tree/           BOM 快照树
GET  /api/versions/{id}/validate/       发布前预检（环 + 冲突）
POST /api/versions/{id}/publish/        发布（违规 400，含 cycles/conflicts）
GET  /api/compare/?from=&to=            两版树形差异
GET/POST/DELETE /api/rules/             替代规则（仅草稿可写）
GET  /api/resolve/?product=&serial=     反查应领物料树
POST /api/issue/                        发料冻结 {product, serial_no, operator}
GET  /api/issues/                       发料记录
```

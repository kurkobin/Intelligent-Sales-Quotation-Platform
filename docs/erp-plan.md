# 智能销售报价平台 · ERP 集成方案（一期：主数据同步）

> 本文档是给「新会话」用的自包含执行说明书。
> 新会话只需读这一份文档即可从零开始执行，**不需要翻聊天记录**。

---

## 0. 一页速览

| 项 | 结论 |
|---|---|
| ERP | 金蝶 **K/3 Cloud（星空）** |
| 本期范围 | **只做主数据同步**：汇率、供应商、料号 |
| 数据方向 | ERP → 报价平台（**单向**，本期不回写） |
| 数据来源 | 全部 mock（本机起一个假 ERP 服务，端口 **9900**） |
| 同步方式 | **全量 upsert** |
| 触发方式 | **管理命令 + 后台按钮** |
| 真 ERP 来了改什么 | 主要改 `erp/adapters/kingdee.py` + `.env` 配置；业务代码/模型/页面不动 |
| 实施状态 | ✅ **1–6 批已全部完成**（2026-11-02），落地细节见 §15 |

---

## 1. 项目现状（新会话必读）

### 1.1 项目路径

```
E:\DeepSeekHarness\prodiction\智能销售报价系统-一期
```

### 1.2 技术栈

- Python 3.14 / Django 6.1.2 / SQLite / uv 管理依赖
- openpyxl（Excel）、cadquery-ocp（3D 解析）

### 1.3 启动命令

```cmd
cd "E:\DeepSeekHarness\prodiction\智能销售报价系统-一期"
uv run python manage.py runserver
```

### 1.4 现有 app 与核心模型

| app | 核心模型 |
|---|---|
| `projects` | `Project`、`VersionHistory`、`UserProfile` |
| `parts` | `Part`（零件、任务分派、3D 尺寸、估价参数） |
| `quotes` | `Quote`、`PackagingItem`、`AssemblyItem`、`SupplierQuote`、`Attachment` |
| `masterdata` | `Supplier`、`StaffMember`、`ExchangeRate`、`WageRate`、`SheetMaterial`、`LineWage`、`StampLabor`、`InjectionParam` |

### 1.5 近期已完成（A/B/C/D）

- **A** 冲压/注塑加工费、注塑材料费、NCT 取值自动化
- **B** `seed_demo_data.py` 灌 mock 主数据；「一键采用」自动估价
- **C** 看板完成度/阻塞项、专案代码自动编码、专案状态、分派邮件通知、附件按专案分组
- **D** 零件清单导出、报价单明细/汇总导出

### 1.6 当前 git 状态（重要）

- 分支 `main`，跟踪 `origin/main`
- 远端：`https://github.com/kurkobin/Intelligent-Sales-Quotation-Platform.git`
- **有未提交改动**（A/B/C/D 那批），执行 ERP 前建议先提交，留回滚点

---

## 2. 本期目标与边界

### 2.1 做

| # | 数据 | 金蝶表单 | 方向 | 落到我们的表 |
|---|---|---|---|---|
| 1 | 汇率 | `BD_ExchangeRate` | ERP → 我们 | `masterdata.ExchangeRate` |
| 2 | 供应商 | `BD_Supplier` | ERP → 我们 | `masterdata.Supplier` |
| 3 | 料号 | `BD_MATERIAL` | ERP → 我们 | **新建 `masterdata.ItemMaster`** |

### 2.2 不做（二期）

报价单推送、客户同步、库存/未税成本查询、ERP 审批流、定时任务

---

## 3. 已确认的决策（用户拍板）

| # | 决策 | 结论 |
|---|---|---|
| 1 | 料号独立表 | **要**，新建 `ItemMaster` |
| 2 | 金蝶汇率三条规则 | **先按 mock**：取即期汇率、按生效日期年份、方向「1 外币 = X RMB」 |
| 3 | 全量还是增量 | **全量** |
| 4 | 触发方式 | **管理命令 + 后台按钮** |
| 5 | 假 ERP 端口 | **9900** |

---

## 4. 金蝶 K/3 Cloud WebAPI 要点（三个坑）

### 坑 1：登录拿 Cookie，不是 token

```
POST {BASE}/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.AuthService.ValidateUser.common.kdsvc
{"parameters": ["数据中心ID", "用户名", "密码", 2052], "format": "json"}
```

返回 `kdservice-sessionid` Cookie，后续请求都要带；会过期，必须用 `requests.Session()` 并在失效时自动重登。

### 坑 2：查询返回「二维数组」，没有字段名

```json
[[1001, "S001", "东莞精密五金"], [1002, "S002", "深圳鑫达"]]
```

必须按传入的 `FieldKeys` **顺序**映射回字典。

### 坑 3：表单 ID 固定

| 数据 | 表单 ID |
|---|---|
| 供应商 | `BD_Supplier` |
| 物料 / 料号 | `BD_MATERIAL` |
| 汇率 | `BD_ExchangeRate` |
| 客户 | `BD_Customer` |

### 查询接口

```
POST {BASE}/K3Cloud/Kingdee.BOS.WebApi.ServicesStub.DynamicFormService.ExecuteBillQuery.common.kdsvc
{"parameters": ["BD_Supplier", {"FieldKeys": "FSupplierId,FNumber,FName",
  "FilterString": "", "OrderString": "", "TopRowCount": 0, "StartRow": 0, "Limit": 2000}]}
```

---

## 5. 数据模型设计

### 5.1 新建 `masterdata.ItemMaster`

```python
class ItemMaster(models.Model):
    erp_id     = models.CharField("ERP内码", max_length=60, blank=True)
    number     = models.CharField("料号", max_length=60, unique=True)
    name       = models.CharField("名称", max_length=200)
    spec       = models.CharField("规格", max_length=200, blank=True)
    unit       = models.CharField("单位", max_length=20, blank=True)
    material   = models.CharField("材质", max_length=100, blank=True)
    unit_price = models.DecimalField("单价", max_digits=14, decimal_places=4, default=0)
    category   = models.CharField("分类", max_length=50, blank=True)
    is_active  = models.BooleanField("启用", default=True)
    synced_at  = models.DateTimeField("最后同步", null=True, blank=True)
```

### 5.2 新建 `erp.ErpLog`

```python
class ErpLog(models.Model):
    action      = models.CharField("动作", max_length=60)   # login / query / save
    entity      = models.CharField("对象", max_length=60)   # BD_Supplier 等
    request     = models.JSONField("请求", default=dict)
    response    = models.JSONField("响应", default=dict)
    ok          = models.BooleanField("成功", default=False)
    error       = models.TextField("错误", blank=True)
    duration_ms = models.IntegerField("耗时(ms)", default=0)
    created_at  = models.DateTimeField("时间", auto_now_add=True)
```

### 5.3 修改 `masterdata.Supplier`

```python
    erp_id    = models.CharField("ERP内码", max_length=60, blank=True, db_index=True)
    number    = models.CharField("供应商编码", max_length=60, blank=True)
    synced_at = models.DateTimeField("最后同步", null=True, blank=True)
```

### 5.4 修改 `masterdata.ExchangeRate`

```python
    erp_id    = models.CharField("ERP内码", max_length=60, blank=True)
    synced_at = models.DateTimeField("最后同步", null=True, blank=True)
```

### 5.5 修改 `parts.Part`

```python
    item_master = models.ForeignKey("masterdata.ItemMaster", null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name="料号", related_name="parts")
```

---

## 6. 字段映射

### 6.1 `BD_Supplier` → `Supplier`

| 金蝶 | 含义 | 我们 |
|---|---|---|
| `FSupplierId` | 内码 | `erp_id` |
| `FNumber` | 编码 | `number` |
| `FName` | 名称 | `name` |
| `FContact` | 联系人 | `contact` |
| `FEmail` | 邮箱 | `email` |

### 6.2 `BD_ExchangeRate` → `ExchangeRate`

| 金蝶 | 含义 | 我们 |
|---|---|---|
| `FExchangeRateId` | 内码 | `erp_id` |
| `FCurrencyId.FNumber` | 币别 | `currency` |
| `FExchangeRate` | 汇率 | `rate` |
| `FBeginDate` | 生效日期 | `year`（取年份） |
| （固定） | 本币 | `base_currency = "RMB"` |

规则：取即期汇率；方向 **1 外币 = X RMB**（USD = 7.20）。

### 6.3 `BD_MATERIAL` → `ItemMaster`

| 金蝶 | 含义 | 我们 |
|---|---|---|
| `FMATERIALID` | 内码 | `erp_id` |
| `FNumber` | 料号 | `number` |
| `FName` | 名称 | `name` |
| `FSpecification` | 规格 | `spec` |
| `FBaseUnitId.FName` | 单位 | `unit` |
| `FMaterialGroup.FName` | 分组 | `category` |
| `FErpClsID` | 属性 | `is_active` 参考 |

单价 `BD_MATERIAL` 不一定有，本期先留 0。

---

## 7. 文件清单

### 7.1 新增

```
erp/
  __init__.py
  apps.py
  models.py                         ErpLog
  admin.py                          ErpLog 只读列表
  client.py                         KingdeeClient：登录/Cookie/超时/重试/日志
  adapters/
    __init__.py
    base.py                         BaseErpAdapter（抽象契约）
    kingdee.py                      ★ 金蝶报文（真接时主要改这里）
    mock.py                         不联网时的假实现
  services.py                       sync_rates / sync_suppliers / sync_items / test_connection
  urls.py                           后台按钮用
  management/
    __init__.py
    commands/
      __init__.py
      erp_sync.py                   python manage.py erp_sync --what=rates|suppliers|items|all
      erp_server.py                 python manage.py erp_server（假 ERP，9900）

mock_erp/
  __init__.py
  server.py                         标准库 http.server，零依赖
  data.py                           mock 供应商/料号/汇率

docs/erp-plan.md                    本文档
```

### 7.2 修改

```
config/settings.py                 加 ERP_* 配置（从 .env 读）
masterdata/models.py               加 ItemMaster；Supplier/ExchangeRate 加 erp_id
masterdata/admin.py                注册 ItemMaster
parts/models.py                    Part 加 item_master
config/urls.py                     注册 erp 的 url
```

---

## 8. 分批执行计划

### 第 1 批：假 ERP + 汇率同步

**做**：`mock_erp/data.py`、`mock_erp/server.py`（`/login` `/query` `/health`）、`erp/client.py`、`erp/adapters/base.py` + `kingdee.py`（先只做汇率）、`erp/services.sync_rates()`、`erp_server.py`、`erp_sync.py`

**验收**
```cmd
python manage.py erp_server      :: 另开窗口常驻
python manage.py erp_sync --what=rates
```
→ `ExchangeRate` 表 3 条，重复运行不重复插入

---

### 第 2 批：供应商同步

**做**：`Supplier` 加 `erp_id/number/synced_at`；adapter 加 `query_suppliers()`；`services.sync_suppliers()`

**验收**
```cmd
python manage.py erp_sync --what=suppliers
```
→ `Supplier` 表 5 条，重复运行不翻倍

---

### 第 3 批：料号 + ItemMaster

**做**：新建 `ItemMaster` + 迁移；`Part.item_master`；adapter 加 `query_items()`；`services.sync_items()`；后台注册

**验收**
```cmd
python manage.py erp_sync --what=items
```
→ `ItemMaster` 表 8 条；`Part` 能选料号

---

### 第 4 批：调用日志 + 后台页面

**做**：`ErpLog` + 迁移；`client.py` 每次调用写日志；`erp/admin.py` 日志列表

**验收**
→ 后台 `/admin/erp/erplog/` 能看到同步的调用记录

---

### 第 5 批：后台「立即同步」按钮 + 连接测试

**做**：`erp/urls.py` + 视图 `/erp/sync/`；页面加按钮；`services.test_connection()`

**验收**
→ 点按钮提示「同步成功：汇率 3 / 供应商 5 / 料号 8」

---

### 第 6 批：故障演示

**做**：关掉假 ERP 时不崩、友好报错；日志记录失败与重试次数；重试 3 次、指数退避 1s/2s/4s

**验收**
```cmd
（先停 erp_server）
python manage.py erp_sync --what=all
```
→ 输出「连接失败，已重试 3 次」，`ErpLog` 有 3 条失败记录，Django 不抛异常

---

## 9. 整体验收标准

| # | 标准 |
|---|---|
| 1 | `python manage.py check` 0 问题 |
| 2 | `python manage.py erp_sync --what=all` 一次同步三张表 |
| 3 | 重复运行 3 次数据条数不变（幂等） |
| 4 | 后台能看到 `ItemMaster` 列表和 `ErpLog` 日志 |
| 5 | 关掉假 ERP 后失败但不崩，日志有记录 |
| 6 | 原有 `verify_project.py` 仍 8/8 通过 |

---

## 10. 命令速查

```cmd
cd "E:\DeepSeekHarness\prodiction\智能销售报价系统-一期"

uv run python manage.py erp_server            :: 启动假 ERP（常驻，转调独立目录）
uv run python manage.py erp_sync --what=all
uv run python manage.py erp_sync --what=rates
uv run python manage.py erp_sync --what=suppliers
uv run python manage.py erp_sync --what=items
uv run python manage.py erp_sync --test       :: 只测连接
uv run python manage.py runserver
uv run python verify_project.py
```

```cmd
:: 假 ERP 也可以完全独立启动（零依赖，只要有 Python 3.10+）
cd "E:\DeepSeekHarness\prodiction\模拟ERP金蝶系统"
启动模拟ERP.bat        :: 自动找 python（本机没有全局 python）
:: 或指定解释器： "..\智能销售报价系统-一期\.venv\Scripts\python.exe" server.py
```

---

## 11. 环境变量（`.env`）

```
ERP_MODE=mock            # mock=本机假 ERP / http=真金蝶 / offline=不联网读种子
ERP_BASE_URL=http://127.0.0.1:9900/K3Cloud
ERP_ACCT_ID=5f2c8a9e6b1d4c3f8e7a0b1c2d3e4f5
ERP_USER=api_user
ERP_PASSWORD=api_password
ERP_TIMEOUT=30
ERP_MAX_ATTEMPTS=3       # 单次调用最多尝试几次（=1 不重试）
# ERP_MOCK_DIR 可选，默认「项目上一级 / 模拟ERP金蝶系统」
```

`.env` 已被 `.gitignore` 忽略。上面的账号密码是假 ERP 的演示值，控制台页面也会显示，方便对照。

---

## 12. 风险与未决

| 风险 | 说明 | 应对 |
|---|---|---|
| 真实报文可能不同 | 按 K/3 Cloud 公开文档写，真接要联调 | 适配器隔离，只改 `kingdee.py` |
| 汇率方向 | 我们定「1 外币 = X RMB」，金蝶可能相反 | 真接时在 adapter 内转换 |
| 料号单价来源 | `BD_MATERIAL` 不一定带单价 | 本期留 0，二期接价格表 |
| 数据量 | 全量在万级会慢 | 本期 mock 量小，二期加分页 |
| Cookie 过期 | 长任务中途失效 | client 检测 401 自动重登 |

---

## 13. 二期预告

1. 报价单推送 ERP（生成销售报价单）
2. 客户资料同步
3. 库存 / 未税成本查询
4. ERP 审批流回传
5. 定时同步（cron / Celery）
6. 金蝶真实联调

---

## 14. 给新会话的开场白

把本文档贴过去，说：

> 「按 docs/erp-plan.md 执行第 1 批。
>  项目在 E:\DeepSeekHarness\prodiction\智能销售报价系统-一期。
>  先读文档，确认理解，然后开始。」

新会话读完文档就能接上，不需要聊天记录。

---

## 15. 实施结果（2026-11-02 完成）

### 15.1 与计划的两处落地差异

| 计划写法 | 实际做法 | 原因 |
|---|---|---|
| `mock_erp/` 放在 Django 项目内，靠 `manage.py erp_server` 启动 | 独立目录 **`E:\DeepSeekHarness\prodiction\模拟ERP金蝶系统\`**，可直接 `python server.py`；`manage.py erp_server` 保留为薄封装 | ERP 是**既有外部系统（黑盒）**，独立进程更贴近真实；二期换真 ERP 直接删目录；且零依赖，不需要 Django 环境 |
| 假 ERP 只有 3 个 WebAPI | 额外带一个**主数据控制台**（`http://127.0.0.1:9900/`） | 演示「ERP 里新增 → 平台同步」和「开启故障模拟」更直观；WebAPI 仍是金蝶那三个 |

目录结构：

```
E:\DeepSeekHarness\prodiction\
├── 模拟ERP金蝶系统\          独立假 ERP（零依赖，不 import django）
│   ├── server.py             HTTP 服务 + 控制台页面
│   ├── api.py                金蝶协议（登录校验、FieldKeys、二维数组）
│   ├── store.py              JSON 文件「数据库」+ 线程锁
│   ├── data.py               种子数据（3 汇率 / 5 供应商 / 8 料号）
│   ├── erp_data.json         运行时数据（自动生成）
│   ├── README.md
│   └── 启动模拟ERP.bat
└── 智能销售报价系统-一期\      只加对接层，原有业务代码未改
    └── erp\                  客户端 / 适配器 / 同步服务 / 命令 / 日志 / 页面
```

### 15.2 交付清单

| 文件 | 作用 |
|---|---|
| `erp/client.py` | 金蝶客户端：ValidateUser 换 Cookie、查询、超时、重试 3 次 + 指数退避、写 ErpLog |
| `erp/adapters/base.py` | 适配器契约 + 共用取值工具（基础资料对象 / [Id,Number,Name] 兼容） |
| `erp/adapters/kingdee.py` | ★ 金蝶报文与字段映射（真接时主要改这里） |
| `erp/adapters/mock.py` | 离线实现（`ERP_MODE=offline`），不联网自检用 |
| `erp/services.py` | `sync_rates / sync_suppliers / sync_items / sync_all / test_connection` |
| `erp/models.py` | `ErpLog` 调用流水 |
| `erp/management/commands/erp_sync.py` | `--what=rates\|suppliers\|items\|all`、`--test` |
| `erp/management/commands/erp_server.py` | 转调独立目录 `server.py` |
| `erp/views.py` `erp/urls.py` `erp/templates/erp/sync.html` | 后台「ERP 主数据同步」页 + 按钮 |
| `masterdata/models.py` | 新增 `ItemMaster`；`Supplier` / `ExchangeRate` 加 `erp_id / number / synced_at` |
| `masterdata/admin.py` | 注册 `ItemMaster`，主数据列表显示内码与同步时间 |
| `parts/models.py` | `Part.item_master`（可空外键，本机迁移 0007） |
| `config/settings.py` | `ERP_*` 配置（`ERP_MODE / BASE_URL / ACCT_ID / USER / PASSWORD / TIMEOUT / MAX_ATTEMPTS / MOCK_DIR`） |
| `config/urls.py` | 挂 `/erp/sync/` |
| `quotes/templates/base.html` | 左侧「系统维护」加「料号主数据（ERP）」「ERP 主数据同步」 |
| `.env` / `.env.example` | ERP 连接配置（`.env` 仍被 gitignore） |

### 15.3 验收结果（全部通过）

| # | 标准 | 结果 |
|---|---|---|
| 1 | `manage.py check` 0 问题 | ✅ System check identified no issues |
| 2 | `erp_sync --what=all` 一次同步三张表 | ✅ 汇率 3 / 供应商 5 / 料号 8 |
| 3 | 重复运行数据条数不变（幂等） | ✅ 连跑 3 次仍为 3 / 5 / 8 |
| 4 | 后台能看到 ItemMaster 与 ErpLog | ✅ `/admin/masterdata/itemmaster/`、`/admin/erp/erplog/` 均 200 |
| 5 | 关掉假 ERP 后失败但不崩、日志有记录 | ✅ 输出「连接失败，已重试 3 次：连接被拒绝…」，exit 1 无 traceback，新增 3 条失败日志 |
| 6 | 原有 `verify_project.py` 仍 8/8 | ✅ 通过 8 项，失败 0 项 |

补充验证：

- **控制台新增 → 同步**：在假 ERP 控制台新增供应商 S006「临时自检供应商」→ `erp_sync --what=suppliers` 显示「新增 1／更新 5／共 6」→ 平台里能查到（erp_id 9001），清理后回到 5 条；
- **ERP 500 故障模拟**：控制台开启故障后同步，同样重试 3 次并友好报错「ERP 服务端错误（HTTP 500）」，不崩；
- **后台按钮**：`/erp/sync/` 点「立即同步（全部）」提示「同步成功：汇率 3 / 供应商 5 / 料号 8」。

### 15.4 同步规则（实现细节）

- **汇率**：只取即期（`FRateTypeId=001`）；`FBeginDate` 取年份；同一 (年份, 币别) 取生效日期最新的一条；方向 `1 外币 = X RMB`；`base_currency` 固定 `RMB`。
- **供应商**：按「内码 → 编码 → 同名且 `erp_id` 为空的旧数据」认领，因此 seed 的 5 家会被就地补上内码而不是新增 5 条；`FForbidStatus=B` → 状态「停用」。
- **料号**：按料号 upsert；取 `FMaterial.FName` 作材质、`FMaterialGroup.FName` 作分类、`FBaseUnitId.FName` 作单位；单价本期留 0。
- **重试**：单次调用最多 **3 次尝试**，失败间隔 1s、2s（配置项 `ERP_RETRY_DELAYS`）；`erp_sync --what=all` 在登录阶段就失败时，后续两张表标「未执行」，不会变成 9 次重试。
- **日志**：每次 HTTP 调用一条 `ErpLog`（登录 / 查询），密码落库前替换为 `***`，查询只存行数 + 前两条样本。

### 15.5 二期衔接

接真金蝶只需三步：

1. `.env` 改 `ERP_MODE=http`、`ERP_BASE_URL`、`ERP_ACCT_ID / USER / PASSWORD`；
2. 字段对不上时改 `erp/adapters/kingdee.py` 里的 `*_FIELDS` 与取值键；
3. 删除 `模拟ERP金蝶系统` 目录（平台不依赖它），`ERP_MOCK_DIR` 相关配置可留可删。

已为二期留好的口子：`erp/adapters/base.py` 的契约、`ErpLog.action` 里预留的 `save`（回写）、`services.sync_one` 可按实体扩展。

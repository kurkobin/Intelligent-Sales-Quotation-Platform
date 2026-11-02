# ERP 集成二期方案（草案）

> 一期（主数据同步）已完成并验收：汇率 / 供应商 / 料号 三张表全量 upsert。
> 本文只写二期要做什么、依赖什么、怎么验收；**代码尚未开始**。

---

## 0. 一句话结论

二期从「只读主数据」升级到「业务单据双向」：**报价单推回 ERP** 是主线，
客户资料、库存/成本查询、审批流回传是配套，定时同步是运维手段，真金蝶联调是前提。

---

## 1. 前置条件（没有这些就不要开工）

| # | 需要什么 | 谁给 | 阻塞哪一项 |
|---|---|---|---|
| 1 | 真金蝶测试环境（地址、数据中心 ID、集成账号、防火墙放行） | IT / ERP 管理员 | 全部 |
| 2 | 销售报价单在 ERP 里的目标单据（`SAL_QUOTATION`？）及必填字段 | 业务 / ERP 顾问 | 报价单回推 |
| 3 | 客户编码规则、信用/结算信息口径 | 财务 | 客户同步 |
| 4 | 库存与未税成本取哪个组织、哪个仓位、是否含税 | 财务 / 采购 | 库存成本查询 |
| 5 | 审批流是「ERP 推平台」还是「平台轮询」 | 业务 | 审批流回传 |
| 6 | 同步频率与失败告警渠道（邮件 / 企业微信） | 运维 | 定时同步 |

---

## 2. 分批计划

### 第 1 批：客户资料同步（最像一期，先做）

- **接口**：`BD_Customer` → `masterdata.Customer`（新表）
- **字段**：内码、编码、名称、联系人、电话、邮箱、结算币别、信用额度
- **做法**：复用一期 `client.py` + 适配器契约，新增 `query_customers()` 与 `sync_customers()`
- **改哪里**：`erp/adapters/kingdee.py`（表单 ID + FieldKeys）、`erp/services.py`、`masterdata/models.py`、迁移、admin、`erp_sync --what=customers`
- **验收**：`erp_sync --what=customers` 幂等；后台可选客户；原 `proj.customer` 文本字段保留兼容

### 第 2 批：库存 / 未税成本查询（只读，风险低）

- **接口**：`STK_Inventory`（即时库存）、`BD_MATERIAL` 价格字段或成本核算表
- **用法**：料号详情页显示「当前库存 / 未税成本 / 最近入库」，不落库、实时查（加 60s 缓存）
- **注意**：ERP 查库存慢，必须带组织/仓位过滤，禁止全表拉
- **验收**：料号页能显示库存；ERP 超时降级为「暂不可用」而不是 500

### 第 3 批：报价单推回 ERP（主线，工作量最大）

- **目标**：报价审核通过后，在 ERP 生成「销售报价单」草稿（不直接提交，留人工确认）
- **实现要点**：
  1. `erp/client.py` 增加 `save()`（`DynamicFormService.Save`），`ErpLog.action='save'` 已经在枚举里预留；
  2. 新增 `erp/adapters/kingdee.py::build_quotation_payload(quote)`——把平台报价单映射成金蝶单据 JSON；
  3. 平台侧加 `ErpDocument` 映射表（本地单据 ↔ ERP 单据号 ↔ 状态），**必须幂等**：同一报价单重复推送只更新不新建；
  4. 失败可重试，人工可在后台重推；
  5. 回写字段：ERP 单据号、推送时间、推送人、状态。
- **验收**：同一报价单连点 3 次推送，ERP 里只有 1 张单据；断网重试不产生重复；后台能看到映射与错误
- **风险**：ERP 必填字段多（组织、币别、税率、结算方式），需要业务先给一张「字段对照表」

### 第 4 批：审批流回传

- **方向**：ERP → 平台（轮询 ERP 单据状态，或 ERP 主动回调）
- **做法**：定时任务按 `ErpDocument` 里的单据号查状态，回写 `Quote.status`
- **注意**：平台已有 `draft/submitted` 两态，需与 ERP 审批状态做映射表，别直接复用

### 第 5 批：定时同步

- **方案**：管理命令 + Windows 计划任务（当前是单机 SQLite，先不引 Celery）
- **命令**：`erp_sync --what=all --quiet`（新增 `--quiet`，供计划任务用）
- **告警**：连续失败 2 次发邮件（已有 `EMAIL_*` 配置）
- **验收**：计划任务跑 7 天，`ErpLog` 有记录、失败有告警

### 第 6 批：真金蝶联调与收尾

- 用第 1 批的客户同步做「最小联调」，再逐个字段对齐
- 把 `.env` 的 `ERP_MODE` 从 `mock` 改 `http`，`ERP_BASE_URL` 指真服务器
- 删除 `模拟ERP金蝶系统` 目录（平台不依赖）
- 回归：`manage.py test`、`verify_project.py`、真实单据推一张到测试账套

---

## 3. 一期已经准备好的东西（二期直接复用）

| 能力 | 位置 | 说明 |
|---|---|---|
| 登录换 Cookie + 401 自动重登 | `erp/client.py` | `login(force=True)`、`query()` 捕获 401 重登 |
| 重试 + 指数退避 | `erp/client.py` | 3 次尝试，1s/2s；`ERP_MAX_ATTEMPTS` 可调 |
| 调用日志 | `erp/models.py::ErpLog` | `save` 动作已预留，密码落库前打码 |
| 适配器隔离 | `erp/adapters/` | 换 ERP 只换实现，服务层不动 |
| 幂等 upsert | `erp/services.py` | `update_or_create` + 认领规则 |
| 离线自测 | `erp/adapters/mock.py` | `ERP_MODE=offline`，测试不依赖网络 |
| 后台按钮/日志页 | `erp/views.py`、`erp/templates/erp/sync.html` | 加实体只需加按钮 |

---

## 4. 需要新增的数据模型（预告）

```python
class Customer(models.Model):        # 第 1 批
    erp_id, number, name, contact, phone, email,
    currency, credit_limit, is_active, synced_at

class ErpDocument(models.Model):     # 第 3 批（回写单据必须可追溯）
    kind          = CharField()      # quotation
    local_id      = IntegerField()   # Quote.id
    erp_bill_no   = CharField()
    status        = CharField()
    pushed_at, pushed_by, error
```

---

## 5. 建议节奏

| 批次 | 依赖 | 粗估 |
|---|---|---|
| 1 客户同步 | 真 ERP 只读权限 | 0.5–1 天 |
| 2 库存查询 | 组织/仓位口径 | 1 天 |
| 3 报价单回推 | ERP 字段对照表 | 3–5 天（含联调） |
| 4 审批回传 | ERP 状态接口 | 1–2 天 |
| 5 定时同步 | 告警渠道 | 0.5 天 |
| 6 收尾联调 | 测试账套 | 1–2 天 |

**建议先做 1 + 5**：客户同步能验证真 ERP 连通性，定时同步能验证长期稳定性，
这两步风险最低；第 3 批是真正的硬骨头，务必等字段对照表确认后再动。
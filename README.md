# 智能销售报价平台（简化版）

基于 Django 的报价平台，实现「专案 → 零件 → 报价 → BOM COST → 报价单」主链，并包含角色权限、任务分派、审批、版本管理、3D 解析。

## 界面预览

**BOM COST 汇总页**

![BOM COST 汇总](images/页面展示.png)

**销售人员视角**（只看得到自己负责的专案）

![销售人员界面](images/销售人员界面.png)

**评估人员视角**（只看到指派给自己的任务）

![评估人员界面](images/评估人员界面.png)

**更多页面**

![页面展示1](images/页面展示1.png)

![页面展示2](images/页面展示2.png)


## 运行环境

- Python 3.11–3.14（原开发环境 3.14）
- Django 6.1.2
- openpyxl
- cadquery-ocp（OpenCascade，用于 3D 解析）

## 安装与启动

```cmd
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

访问 http://127.0.0.1:8000/

> 如果 `cadquery-ocp` 下载太慢，可改用更小的 `cadquery-ocp-novtk`（省掉 77MB 的 VTK，解析功能完全一样）。

## 配置 SECRET_KEY（必做）

本项目**不把 SECRET_KEY 写在代码里**，首次运行前要创建 `.env`：

1. 复制 `.env.example` 为 `.env`
2. 把 `DJANGO_SECRET_KEY` 换成随机字符串，可以用下面的命令生成：

```cmd
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

`.env` 已被 `.gitignore` 忽略，**不会提交到仓库**。没有 `.env` 时会使用一个仅供本地调试的占位 key。

## 功能清单

### 专案管理
- 专案基本信息、归属销售、包材/IE 负责人
- 主/子版本号自动递增
- 版本历史 + 报价快照 + 继承最近快照

### 零件与 3D
- 零件清单、Excel 导入
- **上传 3D 图档（.stp/.step/.igs/.iges）→ OpenCascade 自动解析出零件的包围盒尺寸与体积，生成零件清单**
- **自动材料费**：选好「钣金材料」后，按 `体积 × 密度 ÷ 10⁶ = 重量(kg)`、`重量 × 单价 = 材料费` 自动算出参考值
- 不支持 .x_t（Parasolid 需商业引擎）

### 报价作业
- 任务分派页（5 个零件级角色 + 2 个专案级角色）
- 我的任务 / 我的零件 / 我的开模 / 我的模具采购 / 我的委外采购 / 我的数控加工
- 在线填写报价（材料费/加工费/表面处理费/模具费/委外加工费/委外表处费/NCT加工费）
- 草稿 ↔ 已提交
- 批量下载报价模板 / 上传回填

### 报价产出
- BOM COST 完整公式：零件成本 + 模摊计提 + 不良成本 + 包材费 + 组装费
- **汇率读「汇率维护」表**：按当年、再按该币别最新一年取值，表里没有才回退到默认值；页面会标明汇率来源
- **未税折算**：模具费按含税录入，按专案的增值税率折算成未税后再摊提
- 多币别折算、审核流程、商务版 Excel 导出
- 包材任务、组装任务、供应商多家比价、报价附件库
- 报表查询（BOM COST 查询 / 厂商询价报表）

### 系统维护（8 张主数据表）
供应商名录、部门人员、汇率维护、报价工缴、钣金材料、线别工缴率、冲压人工费、注塑成型参数

## 3D 解析说明

- 支持：`.stp` `.step` `.igs` `.iges`
- 解析内容：每个实体的包围盒尺寸（X/Y/Z，mm）、体积（mm³）
- 入口：BOM COST 页 →「上传3D」
- 解析出的零件分类默认「外购件」，可后续手动修改；零件名默认「零件1、零件2…」

## 目录结构

- `config/`      项目配置
- `projects/`    专案 + 版本历史
- `parts/`       零件 + 任务分派 + 尺寸/体积
- `quotes/`      报价、BOM COST、3D 解析（cad_parser.py）、模板
- `masterdata/`  主数据维护
- `templates/admin/` 后台自定义模板

## 升级注意

本次新增多个模型和字段，升级后务必执行：

```cmd
uv sync
uv run python manage.py migrate
```

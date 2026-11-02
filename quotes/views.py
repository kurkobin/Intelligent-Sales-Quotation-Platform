from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill,Alignment
from datetime import date
from parts.models import Part
from projects.models import Project, VersionHistory
from .models import AssemblyItem, Attachment, PackagingItem, Quote, SupplierQuote
from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.views import LoginView
from django.db.models import Q,Sum
from decimal import Decimal, InvalidOperation
from django.conf import settings
import os
import tempfile

from .cad_parser import parse_cad


def has_role(user, *group_names):
    """判断用户是否属于指定角色之一（超级用户自动放行）"""
    return user.is_superuser or user.groups.filter(name__in=group_names).exists()

def group_required(*group_names):
    """限制只有指定角色组的用户可以访问"""
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if has_role(request.user, *group_names):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied("你没有权限执行此操作")
        return _wrapped
    return decorator

class RememberMeLoginView(LoginView):
    template_name = "login.html"

    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.POST.get("remember_me"):
            self.request.session.set_expiry(60 * 60 * 24 * 30)   # 保持登录：30 天
        else:
            self.request.session.set_expiry(0)                    # 关闭浏览器即失效
        return response

def visible_projects(user):
    """按角色返回可见的专案：成本/超管看全部，销售只看自己的"""
    if has_role(user, "成本人员"):
        return Project.objects.all()
    if user.groups.filter(name="销售人员").exists():
        return Project.objects.filter(owner=user)
    return Project.objects.all()


def get_visible_project(request, project_id):
    """取专案，并检查当前用户是否有权访问"""
    project = get_object_or_404(Project, pk=project_id)
    if not has_role(request.user, "成本人员") and request.user.groups.filter(name="销售人员").exists():
        if project.owner_id != request.user.id:
            raise PermissionDenied("你无权访问该专案")
    return project

@login_required
def home(request):
    projects = visible_projects(request.user)
    return render(request, "quotes/home.html", {"projects": projects})


@login_required
def bom_cost(request, project_id):
    project = get_visible_project(request, project_id)

    rows = []
    total_material = total_process = total_finish = total_mold = 0

    for part in project.parts.all():
        quote = getattr(part, "quote", None)
        material = quote.material if quote else 0
        process = quote.process if quote else 0
        finish = quote.finish if quote else 0
        mold = quote.mold_fee if quote else 0
        subtotal = material + process + finish

        total_material += material
        total_process += process
        total_finish += finish
        total_mold += mold

        rows.append({
            "part": part,
            "material": material,
            "process": process,
            "finish": finish,
            "mold": mold,
            "subtotal": subtotal,
        })

    parts_total = total_material + total_process + total_finish

    # 包材费（专案级）
    packaging_total = sum((item.amount for item in project.packaging_items.all()), Decimal("0"))
    # 组装费（专案级）
    assembly_total = sum((item.cost for item in project.assembly_items.all()), Decimal("0"))

    # 模摊计提成本 =（模具费汇总 - 客户支付模具款）÷ 预测量
    qty = project.forecast_qty or 1
    mold_amortize = (total_mold - project.customer_mold_payment) / qty

    # 不良成本 =（材料成本 + 组装费）× 不良率
    defect_cost = (total_material + assembly_total) * (project.defect_rate / Decimal("100"))

    # 单套成本合计
    grand_total = parts_total + mold_amortize + defect_cost + packaging_total + assembly_total

    is_sales = request.user.groups.filter(name="销售人员").exists()
    can_export = has_role(request.user, "成本人员") or (is_sales and project.bom_status == "approved")
    can_approve = has_role(request.user, "成本人员") and project.bom_status != "approved"
    rate = settings.EXCHANGE_RATES.get(project.currency, Decimal("1"))
    grand_total_local = grand_total / rate if rate else grand_total

    return render(request, "quotes/bom_cost.html", {
        "project": project,
        "rows": rows,
        "total_material": total_material,
        "total_process": total_process,
        "total_finish": total_finish,
        "total_mold": total_mold,
        "parts_total": parts_total,
        "packaging_total": packaging_total,
        "assembly_total": assembly_total,
        "mold_amortize": mold_amortize,
        "defect_cost": defect_cost,
        "grand_total": grand_total,
        "can_import": has_role(request.user, "成本人员"),
        "can_export": can_export,
        "can_approve": can_approve,
        "grand_total_local": grand_total_local,
        "projects": visible_projects(request.user),
    })

@login_required
@group_required("成本人员")
def approve_bom(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    if request.method == "POST":
        project.bom_status = "approved"
        project.save()
    return redirect("bom_cost", project_id=project.id)


@login_required
@group_required("成本人员", "销售人员")
def export_bom_cost(request, project_id):
    """导出商务版报价单（Excel）"""
    project = get_visible_project(request, project_id)

    wb = Workbook()
    ws = wb.active
    ws.title = "报价单"

    # 标题
    ws.merge_cells("A1:F1")
    ws["A1"] = "报 价 单"
    ws["A1"].font = Font(size=22, bold=True)
    ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 38

    # 抬头信息
    ws["A3"] = f"报价单号：QT-{project.id:04d}"
    ws["D3"] = f"报价日期：{date.today().strftime('%Y-%m-%d')}"
    ws["A4"] = f"客户名称：{project.customer}"
    ws["D4"] = f"币别：{project.currency}"
    ws["A5"] = f"专案名称：{project.name}"
    ws["D5"] = "付款条件：月结 30 天"
    for cell in ("A3", "D3", "A4", "D4", "A5", "D5"):
        ws[cell].font = Font(size=11)

    # 空行 + 表头
    ws.append([])
    ws.append(["零件", "分类", "材料费", "加工费", "表面处理费", "小计"])
    for cell in ws[7]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E79")
        cell.alignment = Alignment(horizontal="center")

    # 明细
    total_material = total_process = total_finish = 0
    for part in project.parts.all():
        quote = getattr(part, "quote", None)
        material = float(quote.material) if quote else 0.0
        process = float(quote.process) if quote else 0.0
        finish = float(quote.finish) if quote else 0.0
        subtotal = material + process + finish
        total_material += material
        total_process += process
        total_finish += finish
        ws.append([part.name, part.category, material, process, finish, subtotal])

    # 合计
    grand_total = total_material + total_process + total_finish
    ws.append(["合计", "", total_material, total_process, total_finish, grand_total])
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="EEF3F8")

    # 备注与签核
    ws.append([])
    ws.append(["备注：本报价单为未税价，最终以双方确认合同为准。"])
    ws.append([])
    ws.append(["制表：", "", "审核：", "", "客户确认："])

    # 列宽
    for col, w in {"A": 26, "B": 14, "C": 12, "D": 12, "E": 14, "F": 12}.items():
        ws.column_dimensions[col].width = w

    # 下载
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="Quotation_QT{project.id:04d}.xlsx"'
    wb.save(response)
    return response


@login_required
@group_required("成本人员")
def import_parts(request, project_id):
    """从 Excel 导入零件清单"""
    project = get_object_or_404(Project, pk=project_id)

    if request.method == "POST":
        excel_file = request.FILES.get("file")
        if not excel_file:
            return render(request, "quotes/import.html", {"project": project, "error": "请先选择一个 Excel 文件"})

        wb = load_workbook(excel_file, data_only=True)
        ws = wb.active

        valid_categories = ["冲压钣金件", "NCT钣金件", "注塑件", "外购件"]
        count = 0

        for row in ws.iter_rows(min_row=2, values_only=True):
            name = row[0] if len(row) > 0 else None
            if not name:
                continue
            qty_raw = row[1] if len(row) > 1 else None
            qty = int(float(qty_raw)) if qty_raw not in (None, "") else 1
            category = str(row[2]).strip() if len(row) > 2 and row[2] else "外购件"
            if category not in valid_categories:
                category = "外购件"

            Part.objects.create(
                project=project,
                name=str(name).strip(),
                qty=qty,
                category=category,
            )
            count += 1

        if count:
            project.minor_version += 1
            project.save()

        return render(request, "quotes/import.html", {"project": project, "success": f"成功导入 {count} 个零件"})

    return render(request, "quotes/import.html", {"project": project})

@login_required
def dashboard(request):
    projects = visible_projects(request.user)
    rows = []
    for project in projects:
        part_count = project.parts.count()
        submitted_count = Quote.objects.filter(part__project=project, status="submitted").count()
        totals = Quote.objects.filter(part__project=project).aggregate(
            material=Sum("material"),
            process=Sum("process"),
            finish=Sum("finish"),
        )
        grand_total = (totals["material"] or 0) + (totals["process"] or 0) + (totals["finish"] or 0)
        rows.append({
            "project": project,
            "part_count": part_count,
            "submitted_count": submitted_count,
            "grand_total": grand_total,
        })
    return render(request, "quotes/dashboard.html", {"rows": rows})

@login_required
def my_tasks(request):
    parts = Part.objects.filter(
        Q(molder=request.user) | Q(evaluator=request.user) | Q(purchaser=request.user)
        | Q(mold_purchaser=request.user) | Q(outsource_buyer=request.user) | Q(cnc_engineer=request.user)
    ).select_related("project", "quote")
    return render(request, "quotes/my_tasks.html", {"parts": parts})

def _money(value):
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError):
        return Decimal("0")


@login_required
def edit_quote(request, part_id):
    part = get_object_or_404(Part, pk=part_id)

    allowed = (
        has_role(request.user, "成本人员")
        or request.user in (part.molder, part.evaluator, part.purchaser)
    )
    if not allowed:
        raise PermissionDenied("你没有权限编辑这个零件的报价")

    quote, _ = Quote.objects.get_or_create(part=part)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "unsubmit":
            if has_role(request.user, "成本人员"):
                quote.status = "draft"
                quote.save()
            return redirect("edit_quote", part_id=part.id)

        if quote.status != "submitted":
            quote.material = _money(request.POST.get("material"))
            quote.process = _money(request.POST.get("process"))
            quote.finish = _money(request.POST.get("finish"))
            quote.mold_fee = _money(request.POST.get("mold_fee"))
            quote.outsource_process_fee = _money(request.POST.get("outsource_process_fee"))
            quote.outsource_finish_fee = _money(request.POST.get("outsource_finish_fee"))
            quote.nct_fee = _money(request.POST.get("nct_fee"))
            if action == "submit":
                quote.status = "submitted"
            quote.save()
            if action == "submit":
                return redirect("my_tasks")

        return redirect("edit_quote", part_id=part.id)

    return render(request, "quotes/edit_quote.html", {"part": part, "quote": quote})


@login_required
def my_parts(request):
    """我的零件任务（采购员看指派给自己的外购件）"""
    parts = Part.objects.filter(purchaser=request.user).select_related("project", "quote")
    return render(request, "quotes/my_parts.html", {"parts": parts})


@login_required
def packaging_tasks(request, project_id):
    """我的包材任务（专案级）"""
    project = get_visible_project(request, project_id)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        if name:
            PackagingItem.objects.create(
                project=project,
                name=name,
                part_no=request.POST.get("part_no", "").strip(),
                unit=request.POST.get("unit", "").strip(),
                usage=_money(request.POST.get("usage")),
                unit_price=_money(request.POST.get("unit_price")),
            )
        return redirect("packaging_tasks", project_id=project.id)

    items = project.packaging_items.all()
    total = sum((i.amount for i in items), Decimal("0"))
    return render(request, "quotes/packaging.html", {"project": project, "items": items, "total": total})


@login_required
def assembly_tasks(request, project_id):
    """我的组装任务（专案级）"""
    project = get_visible_project(request, project_id)
    if request.method == "POST":
        step = request.POST.get("step", "").strip()
        if step:
            AssemblyItem.objects.create(
                project=project,
                step=step,
                dept_name=request.POST.get("dept_name", "").strip(),
                headcount=_money(request.POST.get("headcount")),
                capacity_per_hour=_money(request.POST.get("capacity_per_hour")),
                rate_rmb=_money(request.POST.get("rate_rmb")),
            )
        return redirect("assembly_tasks", project_id=project.id)

    items = project.assembly_items.all()
    total = sum((i.cost for i in items), Decimal("0"))
    return render(request, "quotes/assembly.html", {"project": project, "items": items, "total": total})


@login_required
def supplier_quotes(request, part_id):
    """采购员报价填写（外购件多家比价）"""
    part = get_object_or_404(Part, pk=part_id)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "delete":
            SupplierQuote.objects.filter(pk=request.POST.get("sid"), part=part).delete()
        else:
            supplier_name = request.POST.get("supplier_name", "").strip()
            if supplier_name:
                SupplierQuote.objects.create(
                    part=part,
                    supplier_name=supplier_name,
                    currency=request.POST.get("currency", "RMB"),
                    price=_money(request.POST.get("price")),
                    mold_fee=_money(request.POST.get("mold_fee")),
                    quota=_money(request.POST.get("quota")),
                )
        return redirect("supplier_quotes", part_id=part.id)

    quotes = part.supplier_quotes.all()
    max_price = max((q.price for q in quotes), default=0)
    return render(request, "quotes/supplier_quotes.html",
                  {"part": part, "quotes": quotes, "max_price": max_price})


ROLE_TASKS = {
    "mold": ("molder", "模具工程师", "我的开模任务"),
    "moldbuy": ("mold_purchaser", "模具采购", "我的模具采购任务"),
    "outsource": ("outsource_buyer", "委外采购", "我的委外采购任务"),
    "cnc": ("cnc_engineer", "数控工程师", "我的数控加工任务"),
}


@login_required
def role_tasks(request, role):
    """各角色的任务列表（模具工程师/模具采购/委外采购/数控工程师）"""
    if role not in ROLE_TASKS:
        raise PermissionDenied("未知角色")
    field, label, title = ROLE_TASKS[role]
    parts = Part.objects.filter(**{field: request.user}).select_related("project", "quote")
    return render(request, "quotes/role_tasks.html",
                  {"parts": parts, "title": title, "label": label})


@login_required
def report_query(request):
    """报表查询：BOM COST 查询 / 厂商询价报表"""
    projects = visible_projects(request.user)
    project = None
    rows = []
    supplier_rows = []
    pid = request.GET.get("project")
    category = request.GET.get("category", "")
    rtype = request.GET.get("rtype", "bom")

    if pid:
        project = get_object_or_404(Project, pk=pid)
        if rtype == "supplier":
            sq = SupplierQuote.objects.filter(part__project=project).select_related("part")
            if category:
                sq = sq.filter(part__category=category)
            supplier_rows = sq
        else:
            parts = project.parts.all()
            if category:
                parts = parts.filter(category=category)
            for part in parts:
                q = getattr(part, "quote", None)
                rows.append({
                    "part": part,
                    "material": q.material if q else 0,
                    "process": q.process if q else 0,
                    "finish": q.finish if q else 0,
                    "mold": q.mold_fee if q else 0,
                })

    return render(request, "quotes/report.html", {
        "projects": projects,
        "project": project,
        "rows": rows,
        "supplier_rows": supplier_rows,
        "category": category,
        "rtype": rtype,
        "categories": ["冲压钣金件", "NCT钣金件", "注塑件", "外购件"],
    })


@login_required
def attachment_library(request, project_id):
    """报价附件库（按专案归档）"""
    project = get_visible_project(request, project_id)

    if request.method == "POST":
        f = request.FILES.get("file")
        title = request.POST.get("title", "").strip() or (f.name if f else "")
        if f:
            Attachment.objects.create(project=project, title=title, file=f,
                                      uploaded_by=request.user.username)
        return redirect("attachment_library", project_id=project.id)

    items = project.attachments.all()
    return render(request, "quotes/attachments.html", {"project": project, "items": items})


@login_required
@group_required("成本人员")
def assign_tasks(request, project_id):
    """任务分派页（零件级 5 个角色 + 专案级包材/IE）"""
    project = get_visible_project(request, project_id)
    users = User.objects.filter(is_active=True).order_by("username")

    if request.method == "POST":
        for part in project.parts.all():
            part.molder_id = request.POST.get(f"molder_{part.id}") or None
            part.mold_purchaser_id = request.POST.get(f"moldbuy_{part.id}") or None
            part.evaluator_id = request.POST.get(f"eval_{part.id}") or None
            part.outsource_buyer_id = request.POST.get(f"out_{part.id}") or None
            part.cnc_engineer_id = request.POST.get(f"cnc_{part.id}") or None
            part.save()
        project.packaging_engineer_id = request.POST.get("packaging_engineer") or None
        project.ie_engineer_id = request.POST.get("ie_engineer") or None
        project.save()
        return redirect("assign_tasks", project_id=project.id)

    return render(request, "quotes/assign.html", {
        "project": project, "parts": project.parts.all(), "users": users,
    })


@login_required
def download_quote_template(request, project_id):
    """下载报价填写模板（Excel，含零件编号，可原样上传）"""
    project = get_visible_project(request, project_id)

    wb = Workbook()
    ws = wb.active
    ws.title = "报价模板"
    ws.append(["零件编号", "零件名称", "分类", "材料费", "加工费", "表面处理费",
               "模具费", "委外加工费", "委外表处费", "NCT加工费"])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E79")

    for part in project.parts.all():
        q = getattr(part, "quote", None)
        ws.append([
            part.id, part.name, part.category,
            float(q.material) if q else 0,
            float(q.process) if q else 0,
            float(q.finish) if q else 0,
            float(q.mold_fee) if q else 0,
            float(q.outsource_process_fee) if q else 0,
            float(q.outsource_finish_fee) if q else 0,
            float(q.nct_fee) if q else 0,
        ])

    for col, w in {"A": 10, "B": 24, "C": 12, "D": 10, "E": 10, "F": 12,
                   "G": 10, "H": 12, "I": 12, "J": 12}.items():
        ws.column_dimensions[col].width = w

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="QuoteTemplate_{project.id}.xlsx"'
    wb.save(response)
    return response


@login_required
def upload_quote_sheet(request, project_id):
    """上传填好的报价表格（按零件编号对号入座）"""
    project = get_visible_project(request, project_id)

    if request.method == "POST":
        f = request.FILES.get("file")
        if not f:
            return render(request, "quotes/upload_quote.html", {"project": project, "error": "请先选择文件"})

        wb = load_workbook(f, data_only=True)
        ws = wb.active
        count = 0

        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or row[0] in (None, ""):
                continue
            part = Part.objects.filter(pk=row[0], project=project).first()
            if not part:
                continue
            q, _ = Quote.objects.get_or_create(part=part)
            if q.status == "submitted":
                continue
            q.material = _money(row[3] if len(row) > 3 else None)
            q.process = _money(row[4] if len(row) > 4 else None)
            q.finish = _money(row[5] if len(row) > 5 else None)
            q.mold_fee = _money(row[6] if len(row) > 6 else None)
            q.outsource_process_fee = _money(row[7] if len(row) > 7 else None)
            q.outsource_finish_fee = _money(row[8] if len(row) > 8 else None)
            q.nct_fee = _money(row[9] if len(row) > 9 else None)
            q.save()
            count += 1

        return render(request, "quotes/upload_quote.html",
                      {"project": project, "success": f"成功更新 {count} 条报价"})

    return render(request, "quotes/upload_quote.html", {"project": project})


@login_required
def version_history(request, project_id):
    """版本历史 + 继承上一版本"""
    project = get_visible_project(request, project_id)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "snapshot":
            project._snapshot(project.major_version, project.minor_version, project.quote_phase)
        elif action == "inherit":
            latest = project.version_history.first()
            if latest and latest.snapshot:
                for part in project.parts.all():
                    data = latest.snapshot.get(part.name)
                    if not data:
                        continue
                    q, _ = Quote.objects.get_or_create(part=part)
                    if q.status == "submitted":
                        continue
                    q.material = _money(data.get("material"))
                    q.process = _money(data.get("process"))
                    q.finish = _money(data.get("finish"))
                    q.save()
        return redirect("version_history", project_id=project.id)

    return render(request, "quotes/versions.html", {
        "project": project, "history": project.version_history.all(),
    })


@login_required
@group_required("成本人员")
def upload_3d(request, project_id):
    """上传 3D 图档（STEP/IGES）并解析生成零件"""
    project = get_visible_project(request, project_id)

    if request.method == "POST":
        f = request.FILES.get("file")
        if not f:
            return render(request, "quotes/upload_3d.html", {"project": project, "error": "请先选择 3D 文件"})

        suffix = os.path.splitext(f.name)[1].lower()
        if suffix not in (".stp", ".step", ".igs", ".iges"):
            return render(request, "quotes/upload_3d.html",
                          {"project": project,
                           "error": "只支持 .stp/.step/.igs/.iges（.x_t 需要商业 CAD 引擎）"})

        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            for chunk in f.chunks():
                tmp.write(chunk)
            tmp.close()
            items = parse_cad(tmp.name)
        except Exception as e:
            return render(request, "quotes/upload_3d.html",
                          {"project": project, "error": f"解析失败：{e}"})
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

        for it in items:
            Part.objects.create(
                project=project, name=it["name"], qty=1, category="外购件",
                size_x=it["x"], size_y=it["y"], size_z=it["z"], volume=it["volume"],
            )
        if items:
            project.minor_version += 1
            project.save()

        return render(request, "quotes/upload_3d.html", {
            "project": project, "items": items,
            "success": f"解析成功，生成 {len(items)} 个零件",
        })

    return render(request, "quotes/upload_3d.html", {"project": project})
from decimal import Decimal

from django.conf import settings
from django.db import models
from projects.models import Project


class Part(models.Model):
    # 零件分类（决定走哪套估价流程，对应需求书 5.1）
    CATEGORY_CHOICES = [
        ("冲压钣金件", "冲压钣金件"),
        ("NCT钣金件", "NCT钣金件"),
        ("注塑件", "注塑件"),
        ("外购件", "外购件"),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        verbose_name="所属专案",
        related_name="parts",
    )
    name = models.CharField("零件名称", max_length=100)
    qty = models.PositiveIntegerField("数量", default=1)
    category = models.CharField("分类", max_length=20, choices=CATEGORY_CHOICES, default="外购件")
    material = models.CharField("材质", max_length=100, blank=True)
    item_master = models.ForeignKey(
        "masterdata.ItemMaster", null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name="料号", related_name="parts",
    )
    sheet_material = models.ForeignKey(
        "masterdata.SheetMaterial", null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name="钣金材料（自动算重量）", related_name="parts",
    )
    remark = models.CharField("备注", max_length=200, blank=True)

    # ---- 冲压估价参数 ----
    line_wage = models.ForeignKey(
        "masterdata.LineWage", null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name="线别工缴率", related_name="parts",
    )
    stamp_steps = models.PositiveIntegerField("冲压工程数", default=1)
    stamp_labor = models.PositiveIntegerField("冲压人力", default=1)
    stamp_output = models.DecimalField("冲压时产（件/小时）", max_digits=12, decimal_places=2, default=0)

    # ---- 注塑估价参数 ----
    injection_param = models.ForeignKey(
        "masterdata.InjectionParam", null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name="注塑成型参数", related_name="parts",
    )
    cavity_count = models.PositiveIntegerField("穴数", default=1)
    part_weight = models.DecimalField("单件重（g）", max_digits=12, decimal_places=3, default=0)
    runner_weight = models.DecimalField("料头重（g）", max_digits=12, decimal_places=3, default=0)

    # ---- NCT 费用（附件识别后填入）----
    nct_material_cost = models.DecimalField("NCT材料费", max_digits=14, decimal_places=2, default=0)
    nct_process_cost = models.DecimalField("NCT加工费", max_digits=14, decimal_places=2, default=0)

    # 3D 解析结果
    size_x = models.DecimalField("尺寸X(mm)", max_digits=12, decimal_places=2, default=0)
    size_y = models.DecimalField("尺寸Y(mm)", max_digits=12, decimal_places=2, default=0)
    size_z = models.DecimalField("尺寸Z(mm)", max_digits=12, decimal_places=2, default=0)
    volume = models.DecimalField("体积(mm³)", max_digits=18, decimal_places=2, default=0)

    # 任务分派：指派给具体的人
    molder = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name="模具工程师", related_name="mold_parts",
    )
    evaluator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name="评估人员", related_name="eval_parts",
    )
    purchaser = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name="采购员", related_name="purchase_parts",
    )
    mold_purchaser = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name="模具采购", related_name="moldbuy_parts",
    )
    outsource_buyer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name="委外采购", related_name="outsource_parts",
    )
    cnc_engineer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name="数控工程师", related_name="cnc_parts",
    )

    class Meta:
        verbose_name = "零件"
        verbose_name_plural = "零件"

    def __str__(self):
        return f"{self.name}（{self.project.name}）"

    @property
    def weight_kg(self):
        """按 体积 × 密度 估算重量（kg）

        体积单位 mm³ → cm³ 除以 1000；密度单位 g/cm³；克 → 千克 再除以 1000
        """
        sm = self.sheet_material
        if not sm or not self.volume:
            return Decimal("0")
        return (self.volume / Decimal("1000")) * sm.density / Decimal("1000")

    @property
    def material_grams(self):
        """单件克重：注塑用「单重 + 料头」，其他按 体积 × 密度 估算"""
        if self.part_weight:
            return self.part_weight + (self.runner_weight or Decimal("0"))
        return self.weight_kg * Decimal("1000")

    @property
    def auto_material_cost(self):
        """自动材料费 = 单件克重(g) ÷ 1000 × 单价(元/kg)"""
        sm = self.sheet_material
        if not sm or not sm.unit_price:
            return Decimal("0")
        return self.material_grams / Decimal("1000") * sm.unit_price

    @property
    def auto_process_cost(self):
        """自动加工费：冲压 / 注塑 各走一套公式"""
        if self.category == "冲压钣金件":
            lw = self.line_wage
            output = self.stamp_output or Decimal("0")
            if not lw or output <= 0:
                return Decimal("0")
            # 小时工缴 × 工程数 × 人力 ÷ 时产 × (1 + 不良率)
            hourly = lw.rate * self.stamp_steps * (self.stamp_labor or 1)
            per_piece = hourly / output
            defect = self.project.defect_rate or Decimal("0")
            return per_piece * (Decimal("1") + defect / Decimal("100"))

        if self.category == "注塑件":
            ip = self.injection_param
            if not ip or not ip.wage:
                return Decimal("0")
            cavity = self.cavity_count or 1
            # 成型时间(S) 折小时 × 工缴 ÷ 穴数
            return (ip.forming_time / Decimal("3600")) * ip.wage / cavity

        return Decimal("0")

    @property
    def auto_quote_values(self):
        """返回 (材料费, 加工费)，供「一键采用」写入报价"""
        if self.category == "NCT钣金件":
            return self.nct_material_cost, self.nct_process_cost
        return self.auto_material_cost, self.auto_process_cost
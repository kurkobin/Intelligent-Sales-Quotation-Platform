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
    sheet_material = models.ForeignKey(
        "masterdata.SheetMaterial", null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name="钣金材料（自动算重量）", related_name="parts",
    )
    remark = models.CharField("备注", max_length=200, blank=True)

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
    def auto_material_cost(self):
        """自动材料费 = 重量(kg) × 单价(元/kg)"""
        sm = self.sheet_material
        if not sm or not sm.unit_price:
            return Decimal("0")
        return self.weight_kg * sm.unit_price
from django.db import models

from parts.models import Part
from projects.models import Project


class Quote(models.Model):
    STATUS_CHOICES = [
        ("draft", "草稿"),
        ("submitted", "已提交"),
    ]

    part = models.OneToOneField(
        Part,
        on_delete=models.CASCADE,
        verbose_name="零件",
        related_name="quote",
    )
    material = models.DecimalField("材料费", max_digits=12, decimal_places=2, default=0)
    process = models.DecimalField("加工费", max_digits=12, decimal_places=2, default=0)
    finish = models.DecimalField("表面处理费", max_digits=12, decimal_places=2, default=0)

    # 各角色登记的额外成本项（简化版）
    mold_fee = models.DecimalField("模具费（RMB含税）", max_digits=12, decimal_places=2, default=0)
    outsource_process_fee = models.DecimalField("委外加工费（RMB未税）", max_digits=12, decimal_places=2, default=0)
    outsource_finish_fee = models.DecimalField("委外表处费（RMB未税）", max_digits=12, decimal_places=2, default=0)
    nct_fee = models.DecimalField("NCT加工费（RMB）", max_digits=12, decimal_places=2, default=0)

    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default="draft")

    class Meta:
        verbose_name = "零件报价明细"
        verbose_name_plural = "零件报价明细"

    def __str__(self):
        return f"{self.part.name} 报价"

    @property
    def total(self):
        return self.material + self.process + self.finish


class PackagingItem(models.Model):
    """包材项（专案级）"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE,
                                verbose_name="专案", related_name="packaging_items")
    part_no = models.CharField("料号", max_length=50, blank=True)
    name = models.CharField("品名", max_length=100)
    unit = models.CharField("单位", max_length=20, blank=True)
    usage = models.DecimalField("组成用量", max_digits=12, decimal_places=4, default=0)
    unit_price = models.DecimalField("采购单价", max_digits=12, decimal_places=4, default=0)

    @property
    def amount(self):
        return self.usage * self.unit_price

    class Meta:
        verbose_name = "包材项"
        verbose_name_plural = "包材项"
        ordering = ["id"]

    def __str__(self):
        return f"{self.name}（{self.project.name}）"


class AssemblyItem(models.Model):
    """组装工序（专案级）"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE,
                                verbose_name="专案", related_name="assembly_items")
    step = models.CharField("工序名称", max_length=100)
    dept_name = models.CharField("部门", max_length=50, blank=True)
    headcount = models.DecimalField("人力（人）", max_digits=8, decimal_places=2, default=0)
    capacity_per_hour = models.DecimalField("产能（件/H）", max_digits=12, decimal_places=2, default=0)
    rate_rmb = models.DecimalField("工缴费率（RMB/H）", max_digits=12, decimal_places=2, default=0)

    @property
    def cost(self):
        if not self.capacity_per_hour:
            return 0
        return self.headcount / self.capacity_per_hour * self.rate_rmb

    class Meta:
        verbose_name = "组装工序"
        verbose_name_plural = "组装工序"
        ordering = ["id"]

    def __str__(self):
        return f"{self.step}（{self.project.name}）"


class SupplierQuote(models.Model):
    """供应商报价（外购件多家比价）"""
    part = models.ForeignKey(Part, on_delete=models.CASCADE,
                             verbose_name="零件", related_name="supplier_quotes")
    supplier_name = models.CharField("供应商名称", max_length=100)
    currency = models.CharField("币别", max_length=10, default="RMB")
    price = models.DecimalField("单价", max_digits=12, decimal_places=4, default=0)
    mold_fee = models.DecimalField("模具费", max_digits=12, decimal_places=2, default=0)
    quota = models.DecimalField("配额比例(%)", max_digits=6, decimal_places=2, default=0)

    class Meta:
        verbose_name = "供应商报价"
        verbose_name_plural = "供应商报价"
        ordering = ["id"]

    def __str__(self):
        return f"{self.part.name} - {self.supplier_name}"


class Attachment(models.Model):
    """报价附件（按专案归档）"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE,
                                verbose_name="专案", related_name="attachments")
    title = models.CharField("标题", max_length=200)
    file = models.FileField("文件", upload_to="attachments/%Y/%m/")
    uploaded_by = models.CharField("上传人", max_length=50, blank=True)
    uploaded_at = models.DateTimeField("上传时间", auto_now_add=True)

    class Meta:
        verbose_name = "报价附件"
        verbose_name_plural = "报价附件"
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.title

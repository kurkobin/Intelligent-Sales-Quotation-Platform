from django.db import models


STATUS_CHOICES = [("启用", "启用"), ("停用", "停用")]


class Supplier(models.Model):
    """供应商名录"""
    name = models.CharField("供应商名称", max_length=100)
    contact = models.CharField("联系人", max_length=50, blank=True)
    email = models.EmailField("联系邮箱", blank=True)
    category = models.CharField("负责品类", max_length=50, blank=True)
    status = models.CharField("状态", max_length=10, choices=STATUS_CHOICES, default="启用")

    class Meta:
        verbose_name = "供应商"
        verbose_name_plural = "供应商"
        ordering = ["id"]

    def __str__(self):
        return self.name


class StaffMember(models.Model):
    """公司内部部门人员"""
    name = models.CharField("姓名", max_length=50)
    department = models.CharField("部门", max_length=50, blank=True)
    email = models.EmailField("邮箱", blank=True)
    role = models.CharField("角色", max_length=100, blank=True)
    status = models.CharField("状态", max_length=10, choices=STATUS_CHOICES, default="启用")

    class Meta:
        verbose_name = "部门人员"
        verbose_name_plural = "部门人员"
        ordering = ["id"]

    def __str__(self):
        return f"{self.name}（{self.department}）"


class ExchangeRate(models.Model):
    """汇率维护"""
    year = models.IntegerField("年度", default=2026)
    base_currency = models.CharField("本币", max_length=10, default="RMB")
    currency = models.CharField("币别", max_length=10)
    rate = models.DecimalField("汇率（1 本币 = ? 该币别）", max_digits=14, decimal_places=6, default=1)

    class Meta:
        verbose_name = "汇率"
        verbose_name_plural = "汇率"
        ordering = ["year", "currency"]
        unique_together = ("year", "base_currency", "currency")

    def __str__(self):
        return f"{self.year} {self.base_currency}→{self.currency} {self.rate}"


class WageRate(models.Model):
    """报价工缴维护"""
    bu = models.CharField("事业处", max_length=50, blank=True)
    dept_code = models.CharField("部门代码", max_length=30, blank=True)
    dept_name = models.CharField("部门名称", max_length=50, blank=True)
    plant = models.CharField("厂区", max_length=30, blank=True)
    supervisor = models.CharField("主管", max_length=50, blank=True)
    year = models.IntegerField("年度", default=2026)
    labor = models.DecimalField("人工工缴（元/小时）", max_digits=12, decimal_places=2, default=0)
    overhead = models.DecimalField("制费工缴（元/小时）", max_digits=12, decimal_places=2, default=0)

    @property
    def total(self):
        return self.labor + self.overhead

    class Meta:
        verbose_name = "报价工缴"
        verbose_name_plural = "报价工缴"
        ordering = ["-year", "dept_code"]

    def __str__(self):
        return f"{self.dept_name} {self.year} 总工缴 {self.total}"


class SheetMaterial(models.Model):
    """钣金材料维护"""
    brand = models.CharField("品牌", max_length=50)
    material = models.CharField("材质", max_length=50)
    density = models.DecimalField("密度（g/cm³）", max_digits=8, decimal_places=4, default=7.85)
    unit_price = models.DecimalField("单价（元/kg）", max_digits=12, decimal_places=4, default=0)

    class Meta:
        verbose_name = "钣金材料"
        verbose_name_plural = "钣金材料"
        ordering = ["id"]

    def __str__(self):
        return f"{self.brand} {self.material}"


class LineWage(models.Model):
    """线别工缴率维护"""
    plant = models.CharField("生产厂区", max_length=30)
    line = models.CharField("线别", max_length=30)
    machine_count = models.PositiveIntegerField("机台数", default=1)
    setup_hours = models.DecimalField("架模试模工时", max_digits=8, decimal_places=2, default=0)
    rate = models.DecimalField("线别工缴率", max_digits=12, decimal_places=2, default=0)

    @property
    def line_setup_fee(self):
        return self.rate * self.setup_hours

    @property
    def machine_rate(self):
        return (self.rate / self.machine_count) if self.machine_count else 0

    @property
    def machine_setup_fee(self):
        return self.machine_rate * self.setup_hours

    class Meta:
        verbose_name = "线别工缴率"
        verbose_name_plural = "线别工缴率"
        ordering = ["id"]

    def __str__(self):
        return f"{self.plant} {self.line}"


class StampLabor(models.Model):
    """冲压人工费维护"""
    plant = models.CharField("生产厂区", max_length=30)
    labor_per_hour = models.DecimalField("冲压人工费/H", max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = "冲压人工费"
        verbose_name_plural = "冲压人工费"
        ordering = ["id"]

    def __str__(self):
        return f"{self.plant} {self.labor_per_hour}"


class InjectionParam(models.Model):
    """注塑成型参数维护"""
    machine_type = models.CharField("机台类型", max_length=50)
    forming_time = models.DecimalField("成型时间(S)", max_digits=10, decimal_places=2, default=0)
    wage = models.DecimalField("工缴", max_digits=12, decimal_places=4, default=0)
    assembly_capacity = models.DecimalField("组装产能", max_digits=12, decimal_places=2, default=0)
    mold_rack_fee = models.DecimalField("500PCS以下模架费用", max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = "注塑成型参数"
        verbose_name_plural = "注塑成型参数"
        ordering = ["id"]

    def __str__(self):
        return self.machine_type

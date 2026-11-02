from django.db import models
from django.conf import settings


class Project(models.Model):
    # 报价阶段选项
    PHASE_CHOICES = [
        ("样品报价", "样品报价"),
        ("量产报价", "量产报价"),
        ("试产报价", "试产报价"),
        ("客户EC变更报价", "客户EC变更报价"),
        ("季度性报价", "季度性报价"),
    ]
    # 生产厂区选项
    PLANT_CHOICES = [
        ("东莞明鑫", "东莞明鑫"),
        ("东莞兴奇宏", "东莞兴奇宏"),
        ("深圳奇宏", "深圳奇宏"),
        ("深圳新奇宏", "深圳新奇宏"),
        ("越南AVC", "越南AVC"),
    ]
    # 币别选项
    CURRENCY_CHOICES = [
        ("RMB", "RMB"),
        ("USD", "USD"),
        ("NTD", "NTD"),
    ]
    # 产品分类选项
    CATEGORY_CHOICES = [
        ("机构产品", "机构产品"),
        ("散热产品", "散热产品"),
        ("风扇产品", "风扇产品"),
        ("水冷产品", "水冷产品"),
        ("系统产品", "系统产品"),
        ("关键部件", "关键部件"),
    ]
    BOM_STATUS_CHOICES = [
        ("pending", "待审核"),
        ("approved", "已审核"),
    ]

    name = models.CharField("专案名称", max_length=100)
    customer = models.CharField("客户名称", max_length=100)
    model = models.CharField("机种", max_length=100, blank=True)
    forecast_qty = models.PositiveIntegerField("预测量/月", default=0)
    quote_phase = models.CharField("报价阶段", max_length=20, choices=PHASE_CHOICES, default="样品报价")
    plant = models.CharField("生产厂区", max_length=20, choices=PLANT_CHOICES, default="东莞明鑫")
    currency = models.CharField("币别", max_length=3, choices=CURRENCY_CHOICES, default="RMB")
    category = models.CharField("产品分类", max_length=20, choices=CATEGORY_CHOICES, default="机构产品")

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="归属销售",
        related_name="projects",
    )
    packaging_engineer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name="包材工程师", related_name="packaging_projects",
    )
    ie_engineer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name="IE工程师", related_name="ie_projects",
    )

    major_version = models.PositiveIntegerField("主版本号", default=1)
    minor_version = models.PositiveIntegerField("子版本号", default=0)
    bom_status = models.CharField(
        "BOM COST 审核状态",
        max_length=20,
        choices=BOM_STATUS_CHOICES,
        default="pending",
    )
    customer_mold_payment = models.DecimalField("客户支付模具款（元）", max_digits=14, decimal_places=2, default=0)
    defect_rate = models.DecimalField("不良率（%）", max_digits=6, decimal_places=2, default=0)
    tax_rate = models.DecimalField("增值税率（%）", max_digits=5, decimal_places=2, default=13,
                                   help_text="模具费默认按含税录入，BOM COST 里会折算成未税")
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        verbose_name = "专案"
        verbose_name_plural = "专案"

    def __str__(self):
        return self.name

    @property
    def version(self):
        return f"V{self.major_version}.{self.minor_version:02d}"

    def _snapshot(self, major, minor, phase):
        """把当前零件的报价存成一份版本快照"""
        data = {}
        for part in self.parts.all():
            q = getattr(part, "quote", None)
            if q:
                data[part.name] = {
                    "material": str(q.material),
                    "process": str(q.process),
                    "finish": str(q.finish),
                }
        VersionHistory.objects.create(
            project=self,
            major_version=major,
            minor_version=minor,
            quote_phase=phase,
            snapshot=data,
        )

    def save(self, *args, **kwargs):
        # 编辑时判断「报价阶段」是否变化，变了先存快照、再主版本 +1、子版本归零
        if self.pk:
            old = Project.objects.filter(pk=self.pk).first()
            if old and old.quote_phase != self.quote_phase:
                self._snapshot(old.major_version, old.minor_version, old.quote_phase)
                self.major_version += 1
                self.minor_version = 0
        super().save(*args, **kwargs)


class VersionHistory(models.Model):
    """专案版本历史（含报价快照）"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE,
                                verbose_name="专案", related_name="version_history")
    major_version = models.PositiveIntegerField("主版本号")
    minor_version = models.PositiveIntegerField("子版本号")
    quote_phase = models.CharField("报价阶段", max_length=20, blank=True)
    snapshot = models.JSONField("报价快照", default=dict, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    @property
    def version(self):
        return f"V{self.major_version}.{self.minor_version:02d}"

    class Meta:
        verbose_name = "版本历史"
        verbose_name_plural = "版本历史"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.project.name} {self.version}"


class UserProfile(models.Model):
    """用户档案：记录登出时间（Django 自带 last_login，没有 last_logout）"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="profile", verbose_name="用户")
    last_logout = models.DateTimeField("最后登出时间", null=True, blank=True)

    class Meta:
        verbose_name = "用户档案"
        verbose_name_plural = "用户档案"

    def __str__(self):
        return self.user.username

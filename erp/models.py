from django.db import models


class ErpLog(models.Model):
    """与 ERP 的每一次通信留一条流水，出问题直接看报文和错误，不用翻控制台。"""

    ACTION_CHOICES = [
        ("login", "登录"),
        ("query", "查询"),
        ("save", "回写"),
    ]

    action = models.CharField("动作", max_length=60, choices=ACTION_CHOICES, default="query")
    entity = models.CharField("对象", max_length=60, blank=True, help_text="金蝶表单 ID，如 BD_Supplier")
    request = models.JSONField("请求", default=dict, blank=True)
    response = models.JSONField("响应", default=dict, blank=True)
    ok = models.BooleanField("成功", default=False)
    error = models.TextField("错误", blank=True)
    duration_ms = models.IntegerField("耗时(ms)", default=0)
    created_at = models.DateTimeField("时间", auto_now_add=True)

    class Meta:
        verbose_name = "ERP 调用日志"
        verbose_name_plural = "ERP 调用日志"
        ordering = ["-id"]

    def __str__(self):
        state = "成功" if self.ok else "失败"
        return f"{self.created_at:%Y-%m-%d %H:%M:%S} {self.get_action_display()} {self.entity or '-'} {state}"
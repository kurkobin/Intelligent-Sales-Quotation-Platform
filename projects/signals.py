from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver
from django.utils import timezone

from .models import UserProfile


@receiver(user_logged_out)
def record_last_logout(sender, request, user, **kwargs):
    """用户登出时记录时间"""
    if user is not None:
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.last_logout = timezone.now()
        profile.save(update_fields=["last_logout"])

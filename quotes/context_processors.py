def user_groups(request):
    """把当前用户所属角色组名注入模板，便于按角色显示/隐藏菜单"""
    if getattr(request, "user", None) and request.user.is_authenticated:
        return {"user_groups": [g.name for g in request.user.groups.all()]}
    return {"user_groups": []}

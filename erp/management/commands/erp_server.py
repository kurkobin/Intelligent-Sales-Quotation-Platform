# -*- coding: utf-8 -*-
"""启动独立的模拟金蝶 ERP 服务（模拟ERP金蝶系统 目录里的 server.py）。

这里只是个薄封装：真正的服务在那个独立目录里，不依赖 Django。
这样做的好处是文档里的命令统一走 manage.py，而服务本身仍然可以单独 `python server.py` 启动。
"""

import runpy
import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "启动独立的模拟金蝶 ERP 服务（默认 127.0.0.1:9900）"

    def add_arguments(self, parser):
        parser.add_argument("--host", help="监听地址，默认 127.0.0.1")
        parser.add_argument("--port", type=int, help="监听端口，默认 9900")
        parser.add_argument("--data", help="erp_data.json 路径")

    def handle(self, *args, **options):
        mock_dir = Path(getattr(settings, "ERP_MOCK_DIR", "") or "")
        server_py = mock_dir / "server.py"
        if not server_py.exists():
            raise CommandError(
                f"找不到模拟 ERP 服务：{server_py}\n"
                f"请确认 模拟ERP金蝶系统 目录存在，或在 .env 里用 ERP_MOCK_DIR 指定它的路径。"
            )

        argv = [str(server_py)]
        for flag in ("host", "port", "data"):
            value = options.get(flag)
            if value:
                argv += [f"--{flag}", str(value)]

        port = options.get("port") or 9900
        host = options.get("host") or "127.0.0.1"
        self.stdout.write(self.style.HTTP_INFO(f"启动模拟 ERP：{server_py}"))
        self.stdout.write(f"（Ctrl+C 停止；控制台 http://{host}:{port}/）")

        original_argv = sys.argv
        sys.argv = argv
        # server.py 用同目录的 api/store/data 模块；runpy 不会自动加 sys.path，这里手动加
        sys.path.insert(0, str(mock_dir))
        try:
            runpy.run_path(str(server_py), run_name="__main__")
        except KeyboardInterrupt:
            pass
        except OSError as exc:
            raise CommandError(
                f"启动失败：{exc}\n"
                f"端口 {port} 可能已被占用（比如已经开着一个模拟 ERP）。"
                f"换个端口：manage.py erp_server --port 9901"
            )
        finally:
            sys.argv = original_argv
            if str(mock_dir) in sys.path:
                sys.path.remove(str(mock_dir))
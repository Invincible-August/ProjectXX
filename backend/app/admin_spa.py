"""
托管运营后台前端静态资源于 ``/management``（与 API 同端口）。

面向对象封装：路径解析、缺构建提示、静态资源长缓存、SPA 回退。
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope

logger = logging.getLogger(__name__)

_MISSING_BUILD_HTML = """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"/>
<title>后台未构建</title>
<body style="font-family:sans-serif;padding:2rem">
<h1>运营后台尚未构建</h1>
<p>请在仓库执行：</p>
<pre>cd admin
npm install
npm run build</pre>
<p>然后打开：<code>/management/</code></p>
<p>API 仍可用：<code>POST /admin/auth/login</code></p>
</body></html>
"""


class ImmutableAssetsStaticFiles(StaticFiles):
    """Vite 带 hash 的 assets：长期缓存，降低重复带宽。"""

    async def get_response(self, path: str, scope: Scope) -> Response:
        """附加 Cache-Control: immutable（Starlette StaticFiles 为 async）。"""
        response = await super().get_response(path, scope)
        if getattr(response, "status_code", 500) == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


class AdminSpaHost:
    """
    运营后台 SPA 宿主。

    挂载约定：
    - 页面入口 ``/management/``
    - 静态资源 ``/management/assets/*``（长缓存）
    - API 仍为 ``/admin/*``（不经本类）
    """

    def __init__(
        self,
        dist_dir: Path | None = None,
        *,
        url_prefix: str = "/management",
    ) -> None:
        """
        Args:
            dist_dir: ``admin/dist`` 绝对路径；默认推算仓库根。
            url_prefix: URL 前缀（无尾斜杠）。
        """
        repo_root = Path(__file__).resolve().parents[2]
        self._dist = (dist_dir or (repo_root / "admin" / "dist")).resolve()
        self._url_prefix = url_prefix.rstrip("/") or "/management"
        self._index = self._dist / "index.html"
        self._assets = self._dist / "assets"
        # 启动时算一次，避免每个请求 resolve
        self._ready = self._index.is_file() and self._assets.is_dir()

    @property
    def is_ready(self) -> bool:
        """dist 是否可服务。"""
        return self._ready

    @property
    def dist_dir(self) -> Path:
        """构建产物目录。"""
        return self._dist

    def mount(self, app: FastAPI) -> None:
        """
        注册静态资源与 SPA 回退路由。

        Args:
            app: FastAPI 应用。
        """
        if self._ready:
            app.mount(
                f"{self._url_prefix}/assets",
                ImmutableAssetsStaticFiles(directory=self._assets),
                name="admin-assets",
            )
            logger.info(
                "admin SPA mounted prefix=%s dist=%s",
                self._url_prefix,
                self._dist,
            )
        else:
            logger.warning(
                "admin dist missing; build with: cd admin && npm run build (expected %s)",
                self._dist,
            )

        prefix = self._url_prefix
        host = self

        @app.get(prefix, include_in_schema=False, response_model=None)
        @app.get(f"{prefix}/", include_in_schema=False, response_model=None)
        @app.get(f"{prefix}/{{full_path:path}}", include_in_schema=False, response_model=None)
        async def admin_spa_entry(
            request: Request,
            full_path: str = "",
        ) -> Response:
            """SPA 入口：静态文件或 index.html；缺构建返回 503 提示页。"""
            _ = request
            return host.build_response(full_path)

    def build_response(self, full_path: str) -> Response:
        """
        根据子路径构造响应（可供单测直接调用）。

        Args:
            full_path: ``/management/`` 之后的路径。
        """
        if not self._ready or not self._index.is_file():
            return HTMLResponse(content=_MISSING_BUILD_HTML, status_code=503)

        normalized = full_path.replace("\\", "/").strip("/")
        if normalized and ".." in normalized.split("/"):
            return JSONResponse({"detail": "invalid path"}, status_code=400)

        if normalized:
            candidate = (self._dist / normalized).resolve()
            try:
                candidate.relative_to(self._dist)
            except ValueError:
                return JSONResponse({"detail": "invalid path"}, status_code=400)
            if candidate.is_file():
                response = FileResponse(candidate)
                # HTML 入口不长缓存；其它根下文件短缓存
                if candidate.suffix.lower() in {".html", ".htm"}:
                    response.headers["Cache-Control"] = "no-cache"
                else:
                    response.headers["Cache-Control"] = "public, max-age=3600"
                return response

        response = FileResponse(self._index)
        response.headers["Cache-Control"] = "no-cache"
        return response


def mount_admin_spa(app: FastAPI) -> AdminSpaHost:
    """
    便捷函数：创建默认宿主并挂载。

    Returns:
        AdminSpaHost: 便于测试检查 ``is_ready``。
    """
    host = AdminSpaHost()
    host.mount(app)
    return host

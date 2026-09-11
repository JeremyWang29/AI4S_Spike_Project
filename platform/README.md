# AI4S Research Decision Platform

正式研发工程位于本目录；旧 `../ai4s-research-decision-platform/` 仅作为只读迁移来源。

## 本地验证

后端使用 Python 3.12。进入仓库根目录后运行：

```powershell
uv sync --project platform/backend --frozen
uv run --project platform/backend python platform/backend/manage.py check
uv run --project platform/backend python platform/backend/manage.py test
```

前端要求 Node 24.12 或更高的 24.x：

```powershell
npm --prefix platform/frontend ci
npm --prefix platform/frontend test
npm --prefix platform/frontend run build
```

首次本地体验前创建一个受邀测试账号（密码不会写入代码）：

```powershell
$env:AI4S_DEBUG = "1"
uv run --project platform/backend python platform/backend/manage.py migrate
uv run --project platform/backend python platform/backend/manage.py create_test_user researcher --password "请替换为至少8位的本地测试密码"
uv run --project platform/backend python platform/backend/manage.py runserver
npm.cmd --prefix platform/frontend run dev
```

开发模式默认信任 `http://localhost:5173` 和 `http://127.0.0.1:5173` 的 CSRF 来源。其他前端地址通过 `AI4S_CSRF_TRUSTED_ORIGINS` 以逗号分隔显式配置；生产模式不设默认信任来源。

打开Vite显示的本地地址后，可以使用真实会话新建项目，也可以从登录页主动加载八步示例。示例和后续步骤草稿只保存在当前浏览器标签页，并始终标注为交互预览。

部署配置可用测试占位密钥执行静态检查；真实启动前必须提供数据库密码、TLS 证书、受支持的平台规则和许可配置。当前已实现范围与仍需真实环境验证的项目见 [验收登记](docs/ACCEPTANCE.md)，运行与恢复要求见 [运维说明](docs/OPERATIONS.md)。

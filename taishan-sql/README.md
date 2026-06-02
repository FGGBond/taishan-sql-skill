# Taishan SQL Skill

这是一个可独立分发的 Skill 包，包含：

- `SKILL.md`：给 AI 编程工具读取的使用说明。
- `scripts/install.sh`：安装内置 CLI。
- `scripts/cli/`：`taishan-sql` Python CLI 项目。

## 安装

把整个 `taishan-sql/` 目录复制到目标工具的 skills 目录后，**在 skill 根目录**执行：

```bash
bash scripts/install.sh
```

安装脚本会自动检测 `python3`/`python`、升级 pip/setuptools、优先创建 `scripts/.venv`，并生成稳定的 `scripts/taishan-sql` 包装脚本。

安装完成后验证（推荐用包装脚本，不依赖 PATH）：

```bash
bash scripts/taishan-sql doctor
```

## 环境要求

- Python 3.10+（多数机器只有 `python3`，没有 `python`）
- pip（安装脚本会尝试 `ensurepip` 引导）
- 首次安装需要能访问 PyPI
- Edge 或 Chrome 已登录 Taishan / JD SSO

常见问题见 `SKILL.md` 中的 Troubleshooting 表。

## 常用命令

```bash
taishan-sql sources
taishan-sql sources --env test
taishan-sql children --id "appNameXXXsettle-bk"
taishan-sql children --env test --id "appNameXXXsettle-bk"
taishan-sql resolve-db --keyword "settle-bk"
taishan-sql resolve-db --env test --keyword "settle-bk"
taishan-sql query --keyword "settle-bk" --sql "select * from deliver_reward_rule limit 3"
taishan-sql query --app-name "settle-bk" --domain "gate173a.ext.jed.jd.local" --db-name "settle_bk" --sql "select 1"
taishan-sql query --env test --app-name "settle-bk" --domain "gate173a.ext.jed.jd.local" --db-name "settle_bk" --sql "select 1"
```

`sources`、`children`、`resolve-db`、`query` 默认使用生产环境 `https://dbsv5api.jd.com`。测试环境使用 `--env test`，会切换到 `http://testapi.dbsv5.jd.com`。

## 认证

CLI 默认从 Edge、Chrome 读取当前登录用户在 Taishan 相关域名下的 Cookie。不要把 cookie、token 或 ticket 写入仓库或聊天上下文。

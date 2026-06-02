# Skills Repository

这是一个可扩展的 Skill 仓库。每个子目录都是一个可独立分发的 Skill 包，目录根部包含 `SKILL.md`，并可在 `scripts/` 下携带配套 CLI 或脚本。

当前包含：

- `taishan-sql/`：Taishan 数据库平台查询 Skill，内置 `taishan-sql` CLI。
- `curl-cli-builder/`：元 Skill，指导 Agent 将 curl 样本封装为可分发 Skill（spec + CLI + SKILL.md）。

## 分发方式

单独分发某个 Skill 时，只需要打包对应目录。例如分发 Taishan SQL Skill：

```bash
zip -r taishan-sql.zip taishan-sql
```

用户解压后把 `taishan-sql/` 放到目标 AI 编程工具的 skills 目录，然后按该目录内 `README.md` 或 `SKILL.md` 执行安装。

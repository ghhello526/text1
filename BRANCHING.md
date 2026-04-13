# Git 分支工作流规范

本项目采用简化的 Git Flow：

- `main`：发布分支，只保留可发布版本
- `develop`：开发主分支，日常集成代码
- `feature/*`：功能分支，从 `develop` 拉取，开发完成后合并回 `develop`

## 1. 新功能开发（feature）

从 `develop` 创建功能分支：

```bash
git checkout develop
git pull
git checkout -b feature/xxx
```

开发过程中正常提交：

```bash
git add .
git commit -m "feat: add xxx"
```

推送到远程：

```bash
git push -u origin feature/xxx
```

开发完成后，将 `feature/xxx` 合并回 `develop`（建议通过 PR）：

```bash
git checkout develop
git pull
git merge --no-ff feature/xxx
git push
```

## 2. 发布流程（develop -> main）

当 `develop` 达到可发布状态时，合并到 `main`：

```bash
git checkout main
git pull
git merge --no-ff develop
git push
```

可选：打版本标签：

```bash
git tag -a v1.0.0 -m "release v1.0.0"
git push origin v1.0.0
```

## 3. 命名与提交建议

- 功能分支命名：`feature/login`、`feature/chart-opt`
- 修复分支命名：`fix/xxx`（如需）
- 提交信息建议：
  - `feat: ...` 新功能
  - `fix: ...` 修复问题
  - `refactor: ...` 重构
  - `docs: ...` 文档更新

## 4. 保护规则建议（GitHub）

建议在 GitHub 为 `main` 开启分支保护：

- 禁止直接 push 到 `main`
- 必须通过 Pull Request 合并
- 至少 1 人 Review（单人项目可按需关闭）

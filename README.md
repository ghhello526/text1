# 项目说明

## 分支工作流（请先阅读）

本项目采用分支式工作流：

- `main`：发布分支，只保存可发布版本
- `develop`：开发主分支，日常开发与集成都在此分支
- `feature/*`：从 `develop` 创建功能分支，完成后合并回 `develop`
- 发布时：将 `develop` 合并到 `main`

详细规范与命令示例见：`BRANCHING.md`

## 快速开始

```bash
pip install -r requirements.txt
python main.py
```

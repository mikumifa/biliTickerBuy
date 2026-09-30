# 贡献者代码阅读 Dashboard

本项目使用 [Understand Anything](https://github.com/Egonex-AI/Understand-Anything) 的原版 Dashboard 展示代码知识图谱，帮助贡献者快速理解项目结构、关键模块、函数/类关系和推荐阅读路径。

## 初始化

首次拉取本仓库后，初始化 Dashboard 子模块：

```bash
git submodule update --init --recursive tools/understand-anything
```

## 启动

Windows PowerShell：

```powershell
.\tools\start-understand-dashboard.ps1
```

脚本会：

1. 确认 `tools/understand-anything` 子模块已初始化。
2. 使用 `corepack pnpm` 安装 Dashboard 依赖。
3. 构建 `@understand-anything/core`。
4. 以仓库根目录作为 `GRAPH_DIR` 启动原版 Dashboard。

启动后终端会输出带 token 的本地地址，例如：

```text
Dashboard URL: http://127.0.0.1:5173/?token=...
```

请使用带 `token` 参数的完整 URL 打开页面。

## 代码变更后更新 Dashboard

当新增代码、删除模块、调整目录结构或进行较大重构后，通常只需要更新知识图谱快照：

```text
.understand-anything/knowledge-graph.json
```

推荐流程：

1. 在最新代码基础上重新生成 Understand Anything 图谱。
2. 确认 `.understand-anything/config.json` 中的 `outputLanguage` 仍为 `zh`。
3. 运行 Dashboard，检查节点数、层级和导览路径是否符合新的代码结构。
4. 将更新后的 `.understand-anything/knowledge-graph.json` 一并提交。

如果只是新增或重构业务代码，通常不需要更新 `tools/understand-anything` 子模块。

只有在以下情况才建议更新子模块：

- 需要 Understand Anything Dashboard 的新功能或 bug fix。
- 当前固定的 Dashboard 版本无法正确读取新的图谱格式。
- 维护者明确希望同步到新的 Understand Anything 上游版本。

更新子模块时，可以在仓库根目录执行：

```bash
git submodule update --remote tools/understand-anything
```

然后重新运行 Dashboard，确认页面能正常读取 `.understand-anything/knowledge-graph.json`。

## 当前图谱位置

当前图谱快照位于：

```text
.understand-anything/knowledge-graph.json
```

如需让 Dashboard 默认显示简体中文，请保留：

```text
.understand-anything/config.json
```

其中的 `outputLanguage` 应为 `zh`。

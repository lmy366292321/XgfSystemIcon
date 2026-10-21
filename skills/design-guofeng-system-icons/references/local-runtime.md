# 本机固定运行入口

Windows 本机部署使用 `scripts/run-local.ps1` 和 `runtime.local.json`。配置记录已经存在的 Python 绝对路径、可执行文件 SHA-256、Python/Pillow 版本和本地发布号。启动器先核对配置，不依赖系统 `python`，不安装依赖、不修改 PATH 或执行策略；文件缺失、指纹或版本变化时退出2，需核对后再更新配置。

`runtime.local.json` 是本机部署配置，不是跨机器发布的默认路径。迁移机器时选择已有且可用的 Python/Pillow 后单独生成配置；不要复制另一台机器的用户路径。通用 Python 脚本仍可在其他已有依赖的环境直接使用。

以下命令中的技能路径、清单路径和新输出目录应替换成实际绝对路径；在 PowerShell 中执行：

```powershell
$entry = Join-Path $env:USERPROFILE '.codex\skills\design-guofeng-system-icons\scripts\run-local.ps1'
& $entry -Operation doctor
& $entry -Operation check-batch -Arguments @('D:\project\batch-manifest.json', '--output-dir', 'D:\project\qa\new-check')
& $entry -Operation qa-sheet -Arguments @('D:\project\batch-manifest.json', '--output-dir', 'D:\project\qa\new-overview')
& $entry -Operation relation-sheet -Arguments @('D:\project\batch-manifest.json', '--output-dir', 'D:\project\qa\new-relations')
& $entry -Operation test -TestRoot 'D:\project\qa\new-fixtures'
```

`check-icon` 将 `-Arguments` 传给 `check_icon.py`，批量命令同理。输出沿用各工具的退出码：批量检查的1表示检查完成但存在失败或未验证，不等于执行崩溃；check-batch的0要求资源交付关卡完整通过，但仍不授予用户、UI或工程验收。workflow操作将参数交给review_workflow.py；步骤命令成功只证明记录成功，不证明交付通过。测试夹具必须放在项目内，不写安装目录。

纯评审任务从 [批量流程](batch-review.md) 开始，不启动生成或修图。更换技能入口或规则会使已有审阅绑定失效；保留旧意见，实际复核后记录新绑定，不自动将旧结论改成当前通过。

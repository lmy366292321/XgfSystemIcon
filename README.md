# XgfSystemIcon

新国风女性向游戏入口图标设计技能。

## 调用

技能名：`design-guofeng-system-icons`。

```text
使用 $design-guofeng-system-icons，设计“好友拜访”入口图标，沿用现有风格和规格，完成120px验收。
```

支持新增功能、现有图标精修、规格检查、只读批量评审及跨物件画风一致性复查。默认1024×1024透明PNG、102px安全留白、左上受光和统一描边观感；只做120px小尺寸验收。实际制作能力依赖调用环境是否提供图像生成/编辑工具。

已有图标可明确要求只读评审：

```text
使用 $design-guofeng-system-icons，按批次清单检查现有图标，生成120px浅深底对照并逐项评审跨物件画风，不修改原图。
```

## 文件

- [技能入口](skills/design-guofeng-system-icons/SKILL.md)
- [完整设计规范与提示词](skills/design-guofeng-system-icons/references/design-standard.md)
- [参考图](skills/design-guofeng-system-icons/assets)：12张完整图标、6张原像素局部观察图及1张真实尺寸失败反例，均来自本项目现有资源。
- [只读规格检查](skills/design-guofeng-system-icons/scripts/check_icon.py)：需要Python 3与Pillow，检查PNG真实位深、安全区、sRGB标识与120px派生关联；只读，不替代视觉验收。

- [分类参考图库](skills/design-guofeng-system-icons/references/reference-library.md)：制作前及验收固定查看10张，生成输入选1–3张，标注来源与确认状态。
- [画面控制卡](skills/design-guofeng-system-icons/references/visual-control.md)：明确必须保持、允许调整、禁止出现与可检查画面要求。

参考图状态：R01–R09已确认；R10闺蜜、R11节日礼包、R12留言为后续已授权的限定用途参考，具体范围以图库索引为准。不含早期失败反例，不自动批准未来改稿。

- [交付与失败处理方案](skills/design-guofeng-system-icons/references/delivery-review.md)：逐项证据、参考分工、两次失败后换方法、实际UI与效果记录。
- [120px对照验收](skills/design-guofeng-system-icons/references/qa-120.md)：固定10张参考，分开报告文件、视觉、用户接受、UI和工程状态。
- [批次清单与只读验收](skills/design-guofeng-system-icons/references/batch-review.md)：预期项目、文件哈希、导出证据、审阅绑定及批量状态。
- [跨物件画风验收](skills/design-guofeng-system-icons/references/style-transfer-review.md)：区分共用画风、材质允许差异与内容保持项，补充关系组对照。
- [批次清单示例](skills/design-guofeng-system-icons/templates/batch-manifest.example.json)：使用已有参考资产演示结构，不代表待交付图标通过验收。
- [本机固定运行入口](skills/design-guofeng-system-icons/references/local-runtime.md)：Windows可选择已有Python/Pillow并核对指纹与版本，不自动安装依赖。

## 在其他设备使用

克隆本仓库，将 `skills/design-guofeng-system-icons` **整个文件夹**复制到对应客户端的技能目录，保留references、assets、scripts、agents结构。不要只复制SKILL.md。安装位置遵循所用客户端的说明；刷新技能列表或开启新会话后检查是否可发现。

GitHub存放文件不等于所有设备已经安装。当前Work技能副本与GitHub维护源需显式同步，不是自动双向同步；修改先核对版本，避免覆盖另一端修改。

仓库不包含 `runtime.local.json`、本机部署备份、批次报告或本次待验原图。Windows固定入口需要各机器自己的运行配置；缺配置时会明确停止。也可直接用明确选定、已具备Pillow的Python运行通用脚本，不必使用Windows启动器。

## 运行检查

以下命令中的 `python` 应指向已有且具备Pillow的Python；所有报告目录必须是新目录，并位于输入保护目录之外。

```text
python -B skills/design-guofeng-system-icons/scripts/check_batch.py /absolute/path/batch-manifest.json --output-dir /absolute/path/new-check
python -B skills/design-guofeng-system-icons/scripts/build_qa_sheet.py /absolute/path/batch-manifest.json --output-dir /absolute/path/new-overview
python -B skills/design-guofeng-system-icons/scripts/build_relation_sheet.py /absolute/path/batch-manifest.json --output-dir /absolute/path/new-relations
python -B -m unittest discover -s skills/design-guofeng-system-icons/scripts -p "test_*.py" -v
```

测试默认在当前目录的 `.test-fixtures` 下建立并清理自身夹具；也可用进程环境变量 `XGF_TEST_ROOT` 指定可写项目目录。批量检查退出码0表示机器必需项通过，1表示检查完成但有失败或未验证，2表示清单或执行错误。状态与原始证据须保留，不能为得到0而重导出或修改输入。

## 验收边界

文件规格可自动测量；光源、功能识别、视觉重量、描边与噪点需实际查看120px浅深底对照。引擎导入、图集压缩及真机验收未执行时，不能声称上线通过。

本仓库未添加通用开源许可；参考资源的使用权限由项目所有者决定。

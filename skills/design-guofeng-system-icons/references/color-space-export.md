# 色彩空间与导出记录

用于新作从原始返回文件开始的采集，以及旧任务的只读复查。它验证文件声明、证据关联和可重放的导出，不判断配色好坏，不要求证明模型内部色度或屏幕校色。批量 JSON 保留兼容字段 `color_provenance`，含义改为本记录的计算结果；不能直接填写文字 `pass`。

## 采集时机与证据

生成/编辑返回文件后、任何缩放、去背景、裁切或标签处理之前，保留原文件，运行 `collect`。无需询问用户常规技术记录；使用实际任务中的路径与回执，不编造供应商声明或生成时间。

```text
python -B scripts/color_record.py collect /task/raw/source.png --role original --note "本任务实际返回的原始PNG；回执见context" --context /task/records/actual-tool-receipt.json --output /task/records/source-color.json
```

`--context` 可重复，回执不存在时省略并在 note 写明缺少，不能创建假回执。记录采集时间、文件SHA-256、PNG声明、ICC配置摘要和像素指纹；这些是本次测得的数据，不冒充历史生成时记录。原图无ICC并不自动表示颜色错误。

`collected_at` 与导出/复查记录的 `recorded_at` 必须存在、包含时区、非未来时间，并且记录时间不早于采集。验证时间字段格式与顺序只证明记录完整性，不能独立证明填写者当时确实执行过，也不能倒推历史生成时间。

- `--role original` 只用于确实保留的原始输入/生成返回文件；不能把后期补标签的交付图当原图。
- 只有最终高清而缺原图时用 `--role working-master`，明确只能复验当前高清到120px，来源仍未验证。
- 已知标记只是后期假设补写，即使PNG带sRGB也必须 `--knowledge unknown`。不能因为标记通过就推翻已知的来源缺口。
- 当前自动支持8位RGB/RGBA PNG：合法sRGB声明，或可由LittleCMS读取并建立转换的RGB ICC。ICC名称含“sRGB”不作为判断依据；cICP、其他格式/位深不猜测为已知来源。原声明冲突/损坏须定位，不能套用假设掩盖。
- 生成端色彩约定可以作为真实context证据保存，但当前工具不自动把自由文字或网页标题升级为来源通过。要新增供应商适配，先取得与实际工具/版本相符的声明和回执，再实现、测试适配。

## 新文件导出

先确认此操作符合当前制作授权。只读审核和已确认图标默认走下一节的 `audit`，不为了新规则重写旧图。以下命令写全新目录，不覆盖任何输入或旧记录。

```text
python -B scripts/color_record.py export /task/records/source-color.json --output-dir /task/candidates/export-01
```

已知原图sRGB：保持其颜色解释；有效RGB ICC：用实际源配置转换到工具保存的sRGB目标配置，再导出明确sRGB PNG，保留alpha。保存Pillow/LittleCMS版本、算法、源/目标配置指纹、源/高清/120文件指纹，验证时实际重放。

当前几何适配仅支持正方形完整画布等比例缩放到1024，再由完整1024缩到120，默认LANCZOS；原1024不再缩放。**不裁边、去底、清噪点、自动居中或修安全区。** 硬规格和视觉审核仍独立执行，不能把这个导出成功当图标合格。不符合该几何路径的制作记录需另外实现真实适配；不能把缺失步骤写成“无转换”。

## 来源未知时

默认 `export` 停止并解释缺口，不创建导出目录。代理根据当前任务在以下两条真实路径中选择；没有依据时保留未知，不需要每张图都向用户追问技术信息。

1. **保留未知**：用于保真、排查或候选制作，保持现有色彩声明与像素解释，只执行明确的完整画布缩放：

   ```text
   python -B scripts/color_record.py export /task/records/source-color.json --unknown preserve --output-dir /task/candidates/preserve-01
   ```

2. **明确工作假设**：确有项目决定按sRGB解释未标记输入时，保存决定及其依据、适用范围、未知限制，再传 `--unknown assume-srgb --basis /task/inputs/color-decision.md`。这仅指派sRGB解释，**不是从已知其他色域转换到sRGB**。有已知ICC时走真实转换，不用假设覆盖配置。没有现成用户决定时，代理可为获准制作的新候选写明自己的工作假设，不冒充用户批准；已确认图标不能由此获得改色授权。

两条路径均可得到“记录完整、导出复验通过”，但 `source.status` 和整体色彩项继续 `unverified`，最终完整交付不得标通过。按实际结果分别报告：视觉已审核／导出可复验／来源未验证。未知原因集中引用同一份项目决定或生成工具证据，不为每张图重复编写空洞免责声明。记录完整性、来源可信范围、导出正确性是三个不同结论。

默认 `--unknown stop` 返回退出码1、`status=unverified`、`action=stopped`，不创建输出目录。这是预期的来源未知分支；命令/输入错误才返回2。

## 旧任务只读复查

只保留当前可取得的原图与历史记录。使用当前采集时间，不倒填历史；沿用已确认文件原样：

```text
python -B scripts/color_record.py collect /task/raw/source.png --role original --note "当前补采集，历史生成时间未证明" --output /task/recheck/source-color.json
python -B scripts/color_record.py audit /task/recheck/source-color.json --master /task/accepted/icon-1024.png --preview /task/accepted/icon-120.png --output /task/recheck/color-export.json
python -B scripts/color_record.py verify /task/recheck/color-export.json --output /task/recheck/color-verification.json
```

`audit` 测试当前支持的完整画布路径是否精确匹配，不声称历史上执行过该命令。源图到高清不匹配时，标记处理链缺失/不支持；高清到120另行复验，不连带否定已完成子项。历史外部导出算法未支持时保留未验证，不更换旧预览来凑通过。仅有最终高清可用working-master角色采集，仍不能还原缺失源图。

## 接入固定审核流程

在批次每项新增：

```json
"color_record": {"path": "/task/recheck/color-export.json", "sha256": "该记录文件实际SHA-256"}
```

在 `files` 阶段前完成并绑定该记录。`check_batch.py` 会重新读原始来源、配置、工作假设和输出文件，校验哈希并重放，不信任保存的通过状态。记录指纹进入当前审核绑定；更换记录、输入或规则后须重做受影响审核，不给旧意见自动换哈希。

清单提供 `item.source` 时，必须与色彩记录的原文件绝对路径和实际SHA-256一致。制作模式同时要求它对应最后一次成功生成的输出；不同源文件各自有合法记录也不能拼接通过。旧任务review模式缺少生成回执时保留缺口，不补造生成事件。

`collect` 的0只表示采集完成；`export/audit/verify` 的0只表示本色彩空间及导出范围通过，1表示失败/未验证，2表示命令或输入错误。所有色彩结果均不替代整体 `delivery.status`、用户接受或游戏引擎验证。原 `color_provenance` 人工报告继续保留作历史记录；无新可复验记录不能授予当前通过。

Windows固定入口为 `run-local.ps1 -Operation color-record -Arguments @(...)`。测试源码包括真实变换、未知/假设分支、拒绝覆写和篡改；合成夹具的通过不作为真实图标的来源证据。

技术依据：[PNG色彩空间声明](https://www.w3.org/TR/png-3/#11sRGB)、[Pillow ICC转换](https://pillow.readthedocs.io/en/stable/reference/ImageCms.html#PIL.ImageCms.profileToProfile)。声明、转换与独立色度验证分别表述。

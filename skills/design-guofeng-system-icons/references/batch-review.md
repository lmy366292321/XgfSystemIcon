# 批次清单与只读验收

多图制作、批量交付或复查时使用。设计规范、参考授权和视觉标准继续以原有文档为准。本入口只增加清单关联、批量机器检查与120px对照编排，不自动判断画风或完成用户／UI／工程验收。

## 清单

从 [示例清单](../templates/batch-manifest.example.json) 复制并填写本次任务；示例使用既有图库文件，只演示合同，不是待交付的新作品。所有路径相对清单文件所在目录解析，也支持只读绝对路径。每份文件描述为 `{"path": "...", "sha256": "64位真实哈希"}`，内容变更后重新记录哈希，不自动改写旧证据。

| 字段 | 用法 |
|---|---|
| `schema_version`／`batch_id`／`expected_ids` | 当前版本1；预期ID来自任务清单，不由现存文件数量推断 |
| `skill`／`rules` | 技能入口和生效规则的文件描述；规则数组每项包含 `id` 与 `file` |
| `references` | 固定10张正式完整参考；每项 `id`、`file`、`purpose`、`limits`。不足时批量报告保留缺口，对照工具不伪造补齐 |
| `items` | 每项 `id`、`name`、`version`、`requirements`、`control_card`、`master`、`preview`、`export` |
| `requirements` | `action`、`subject`、非空 `keep` 列表、`name_dependency`；字段存在不代表图中语义已通过 |
| `export` | `library`、`version`、`resample`、`complete_canvas`、`alpha_handling`、`color_conversion`；外部证据另填 `evidence` 与 `record_name` |
| `previous_preview` | 可选，120px修改前文件；不占10张正式参考名额 |
| `inventory_dirs` | 只枚举指定目录的额外PNG，额外草稿不计入完成数 |
| `protected_roots` | 可选只读源根目录；禁止将输出写到其内部 |
| `visual_review`／`color_provenance` | 可选的已绑定审阅记录；默认未验证 |
| `other_states` | 用户接受、实际UI、工程等原始记录；脚本仅展示，不授予通过 |
| `comparison_groups` | 可选P2关系组；每组 `id`、`purpose`、`members`。成员为 `{"role":"reference或candidate","id":"清单中的ID"}`，每组2–5格 |

不同入口复用相同高清会提示语义复核，但不一概禁止合法复用。清单中的重复ID或缺行报错，缺文件仍保留项目行。原图、控制卡、参考与证据均按当前字节核对；目录中的文件名不替代哈希证据。

## 执行

Windows 本机已部署环境使用 [固定运行入口](local-runtime.md)，分别选择 `check-batch`、`qa-sheet`、`relation-sheet` 和 `test` 操作。以下通用命令用于已明确选定且具备Pillow的Python 3，不自动安装依赖：

```text
python -B scripts/check_batch.py /absolute/path/batch-manifest.json --output-dir /absolute/path/new-check-run
python -B scripts/build_qa_sheet.py /absolute/path/batch-manifest.json --output-dir /absolute/path/new-sheet-run
```

输出目录必须是新目录，且不在原图目录、参考目录或指定保护根内。工具不覆盖历史报告，不改写原图、预览、元数据或安装环境。

批量检查生成 `batch-report.json` 与 `batch-report.md`。JSON保留单图检查器的原始字段、逐项状态、输入快照与审阅绑定。退出码0表示本次机器必需项通过；1表示检查完成但有失败／未验证；2表示清单或执行错误。0不代表视觉、用户接受或上线通过。

PNG尺寸、安全区、真实位深与色彩声明复用 `check_icon.py`。状态区分 `pass`、`fail`、`unverified`、`error`。缺失sRGB声明是色彩未验证，不掩盖已通过的尺寸检查，也不为得到绿色结果自动添加标签。

### 派生边界

- Pillow记录的版本必须与运行环境一致；支持现有检查器的算法，`alpha_handling` 写 `Pillow RGBA resize`，`color_conversion` 写 `none`，`complete_canvas` 为true。其他流程不猜测参数。
- Sharp历史报告只核对报告文件哈希、唯一 `record_name`、高清与120哈希，以及 `preview_export` 中库、版本、算法、完整画布和原始核对结果。字段采用当前制作的 `导出测量.json` 格式。
- 无Sharp复验适配器时，历史记录匹配可显示 `external_record.status=pass`，但当前 `derivation.status` 仍为 `unverified`、`replayed=false`。不能冒充本次Pillow或Sharp复验。
- 未知库、版本不符或缺少证据保持未验证；已知报告与文件不匹配时标失败。不自动改算法、重导出或修复输入。

## 120px对照

输出浅底 `#F4EDE1` 与深底 `#293139` 两组PNG和 `sheet-index.json`。每页固定10张参考，5列×2行；候选与可选修改前图另列，每页最多10个候选／旧稿格，超出分页。每格完整画布120×120，名称映射、文件哈希、版本与格坐标写入索引，图内只标参考ID或项目ID／版本。

正式参考从完整1024画布以当前Pillow LANCZOS生成检查用120副本；候选直接使用已交付120文件，不裁切、不缩放、不重导出。索引明确两者处理路线，不能用检查用参考派生来改写历史参考的技术验收。

`sheet-index.status=pass` 只表示编排完成且输入稳定。查看窗口若缩放，不能称实际120px视觉已验收；按 [qa-120.md](qa-120.md) 实际检查并记录结果。布局代码不计算画风相似度。

## 绑定已有审阅

跨物件任务按 [style-transfer-review.md](style-transfer-review.md) 设置关系组，再运行 `python -B scripts/build_relation_sheet.py manifest.json --output-dir new-relations`。每组各输出浅深底一页，索引保留名称映射但图中只显示ID。此工具复用固定对照的像素与输出保护逻辑，不替代10张参考总览。P2清单有 `comparison_groups` 时，组定义也进入审阅绑定；顺序、成员或目的改变后旧意见待复查。没有该字段的P0–P1清单保留原绑定格式。

批量结果中每项的 `binding_for_review` 包含当前高清／120、控制卡、技能、规则组、参考组和需求内容的指纹。审阅者查看实际图片后，才可将这些值记录到审阅的 `bound`；复制绑定本身不代表已审阅。

视觉记录另需 `reviewer`、`reviewed_at`、`evidence`（审阅正文文件描述）、至少两份浅深底 `sheets` 文件描述，以及 `items`：

- `semantics`、`weight`、`structure`、`materials`、`lighting_outline`、`edges`、`keep`；
- 每项填写 `status`（pass/fail/unverified）、`observation` 与 `location`，在观察正文中写明主要参照。

缺字段、文件改变、规则／控制卡／需求改变，意见保留但标为 `stale`，当前状态未验证。仅有旧Markdown验收正文时可填 `legacy_evidence`，不自动生成当时不存在的完整绑定。工具导入意见不冒充新的独立审阅。

色彩来源意见也需 `bound`、`reviewer`、`reviewed_at`、`evidence`、`statement` 和 `status`。它是人工核对来源／转换链的证据，不是PNG标签自动推导，也不是本工具测得的色度。用户确认不能代替色彩检查。

P0–P1采取保守失效：文件字节变更就待复查；不自动实现“元数据变了但像素未变”的意见继承。需要继承时由审阅者核对并记录新的绑定。批内输入在检查过程中变化时整批报错，不能使用该次通过结论。

## 验证工具改动

```text
python -B -m unittest discover -s scripts -p "test_*.py" -v
```

批量测试只在新建临时夹具中模拟漏图、错配、损坏、规则变化、历史记录与输出保护。真实素材验证时保存前后哈希与报告，技术成功不升级画风结论或参考授权。

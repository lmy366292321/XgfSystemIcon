# 配色计划与固定审核流程

本流程适用于新任务和新复查，不追溯修改已确认图标或历史结论。固定步骤保障证据完整；实际看图仍由审阅者执行，脚本不评审美，也无法证明填写的观察是真实的。

## 设计约束

- 共用画风是线条、受光、色块概括和细节层级；不绑定色相、白花、青瓷或金边。画风参考和配色参考分别选择，后者可以为空并说明独立设计依据。
- 每枚写主色及主物、辅色、点缀色、主辅层级、选择依据和颜色来源。先看整组主色分布，再生成；不要只改小装饰色、让所有大主体仍然青绿。
- 青绿允许使用。植物本色、玉材质、既有物品身份或用户要求均可支持重复颜色；不设机械色数/比例，也不把一批强制涂成彩虹。重复是否单调由整组120px观察决定。
- 已确认图标仅复查时 `preserve_existing=true`，保留其颜色；新规范不构成改色授权。

## 固定步骤及命令

路径使用绝对路径，或清单支持的相对路径。计划、工作流内全部文件描述使用绝对路径及真实SHA-256。建议将计划/控制卡放 `inputs/`，工具回执与色彩记录放 `records/`，工作流阶段放独立 `workflow/`，对照放 `qa/`，审阅正文放 `reviews/`。每次记录输出用新文件名，禁止覆盖输入或旧记录。

1. 按[完整组合区域流程](composition-layout.md)确定布局与资源，将配置路径和SHA-256写入控制卡；准备10张正式参考和 `design-plan.json`；制作前执行 `start`。计划只包含已有参考、控制卡和输入图，不要求未来成图已经存在。
2. 新建/修改图像后，保存真实调用输入、输出及回执，立即按[色彩空间与导出记录](color-space-export.md)采集原始文件，再按composition-layout.md把组合位置写进PNG留白、将UI额外补偿归零，记录真实变换链并建立批次清单。记录 `generated`。纯复查跳过生成，只读collect/audit并明确是本次补采集，不倒填历史。
3. 将计划文件描述填入清单 `design_plan`，每项填入实际 `color_record` 文件描述，并绑定控制卡使用的`layout`；例外可由v2 `geometry`提供同一布局。先运行色彩verify，再记录 `files`，执行真实技术检查；失败/未验证仍可继续诊断，但最终不通过。
4. 用原有工具创建固定十参考浅深底及关系面板，将索引描述填入 `qa_index`、`relation_index`。多图关系组必须覆盖全部候选。实际查看所有页面及交付PNG在UI零额外补偿下的完整组合，将组合证据及配置/资源哈希写入审阅正文，相关结论并入现有八项；填写整批配色及关系意见，再记录 `visual`。
5. 对图标及组合单独第二遍查看；填写 `visual_recheck` 与 `palette_recheck`，记录 `recheck`。可独立或同人复查，必须如实注明；误报/连续失败加强检查，不能复制首遍正文冒充第二遍。
6. 将最后记录的文件描述填入清单 `workflow`，运行 `check_batch.py`。只有 `delivery.status=pass`、退出码0，才称资源交付审核通过。组合检查缺口必须反映在相关视觉项，不能靠脚本退出码核销。用户接受、引擎和真机验收另列；脚本核对布局及嵌套资源、UI零补偿，例外另核对边界和变换；真实遮挡与引擎坐标仍需实际验证。

```text
python -B scripts/review_workflow.py start /task/inputs/design-plan.json --output /task/workflow/01-plan.json --actor maker
python -B scripts/review_workflow.py record /task/workflow/01-plan.json --manifest /task/manifest.json --stage generated --evidence /task/reviews/calls.json --output /task/workflow/02-generated.json --actor maker
python -B scripts/review_workflow.py record /task/workflow/02-generated.json --manifest /task/manifest.json --stage files --output /task/workflow/03-files.json --actor maker
python -B scripts/build_qa_sheet.py /task/manifest.json --output-dir /task/qa/overview
python -B scripts/build_relation_sheet.py /task/manifest.json --output-dir /task/qa/relations
python -B scripts/review_workflow.py record /task/workflow/03-files.json --manifest /task/manifest.json --stage visual --output /task/workflow/04-visual.json --actor reviewer
python -B scripts/review_workflow.py record /task/workflow/04-visual.json --manifest /task/manifest.json --stage recheck --output /task/workflow/05-recheck.json --actor reviewer
python -B scripts/check_batch.py /task/manifest.json --output-dir /task/final-check
```

`review`模式的files直接接01-plan；单图无关系组时不运行关系工具。Windows固定入口新增 `-Operation workflow -Arguments @('start', ...)`。示例命令中的观察记录需实际填写，不能运行命令自动得到美术结论。

`record`可以重做已有阶段，但只写新记录并删除其后的阶段：例如重做files后必须重做visual/recheck。图像、控制卡、参考、规则或配色计划改变会使绑定失效。计划/控制卡变化须另建计划并start；制作中更换输入须在下次调用前重新封存计划，不倒填。旧任务仅有历史记录时用review模式新复查，不伪造原制作时的plan/generated事件。

## 计划格式

顶层：`schema_version:1`、`mode:create|revise|review`、`batch_id`、`batch_palette_reason`、`references`、`items`。references复制本次清单10张的id/file/purpose/limits，文件描述转为绝对路径。items顺序与清单expected_ids一致；每项：

```json
{
  "id": "01",
  "control_card": {"path": "/task/inputs/control-01.md", "sha256": "真实64位SHA-256"},
  "palette": {
    "dominant": "暖陶红：容器主体",
    "secondary": ["米白：标签"],
    "accent": [],
    "reason": "容器材质及与同排纸册的区分",
    "color_source": "独立设计；画风参考不供色",
    "hierarchy": "120px第一眼见容器暖色块，标签为次级",
    "preserve_existing": false
  },
  "style_reference_ids": ["R02"],
  "color_reference_ids": [],
  "generation_inputs": [
    {"role": "style", "file": {"path": "/skill/assets/tea.png", "sha256": "真实64位SHA-256"},
     "purpose": "瓷器概括、描边与受光", "limits": "不继承杯形、茶面、花纹及颜色"}
  ]
}
```

颜色仅为字段示例，不能成为新默认。review模式generation_inputs为空。revise模式额外包含edit_target；外部内容依据使用content角色。style/color必须来自各自声明的正式参考，共1–3张。未确认候选不能标成正式画风/配色输入。

## 生成证据

`calls.json`含非空`calls`数组，每项：`item_id`、带时区`at`、`tool`、`outcome:success|failed`、`inputs`（与计划generation_inputs完全一致）、`receipt`文件描述；成功另有`output`原生成图描述。清单每项`source`绑定最后一次成功调用的原生成图，随后按记录导出高清/120。保留所有本轮尝试，失败不能假写成功，每项至少一个成功源。记录的是已有调用证据，脚本不发起生成、不计费、不冒充可独立核实后端调用。

## 视觉证据格式

每枚 `visual_review`沿用batch-review.md格式，必须含八项：semantics、weight、structure、materials、lighting_outline、edges、keep、palette。每项status、observation、location非空。`bound`从当次check_batch输出的binding_for_review取得；初检报告的delivery未验证是正常的。检查工具永不自动填写pass。

第二遍 `visual_recheck`结构相同，另写`method:independent|same_reviewer_second_pass`。independent必须有不同reviewer；正文是另外的文件。所有reviewed_at为实际观察结束的带时区时间，不早于上一阶段；不要复制旧日期。首遍失败不能被第二遍通过直接抵消，须处理后重新执行首遍及第二遍。

整批 `palette_review`与`palette_recheck`均为：

```text
bound: 上一步工作流记录最后事件的bound（当前批次及计划指纹）
reviewer / reviewed_at: 实际审阅者及时间
status: pass / fail / unverified
item_ids: 与expected_ids相同的完整数组
observation / location: 整组实际主色所见及位置
repetition_reason: 重复主色的依据、是否单调或混淆；无重复也明确记录
hierarchy: 各图主辅层级及整组协调判断
evidence: 本遍实际审阅正文文件描述
sheets: [{background:"#F4EDE1",file:{path,sha256}}, {background:"#293139",file:{path,sha256}}, ...]
relations: {关系组ID:{status,observation,location}, ...}；单图无关系组为{}
```

sheets覆盖qa_index所有页面，不能只验第一页。脚本核对索引版本、全部候选/关系组、两底120px像素与当前源图的对应；证据文件和所有意见绑定当前版本。请把差异写具体，不能用“整体协调”重复填表。

## 能证明与不能证明

- 完整合成夹具可验证顺序、缺项阻断、失效与退出码，不能证明新审美改善。
- 真实旧图只读复查可验证工具链与实际看图记录，不能证明制作前计划能改善新生成结果。
- 新真实制作才能验证配色改善、漏判率和返工次数；本次不为验证技能擅自重绘已确认图。
- 这些脚本约束使用它们的工作流，不能从软件层强迫任意聊天执行所有命令；不得宣称无法绕过。正式交付必须展示最终报告，未运行等同未验证。

# 生成前构图检查

2026-10-23修复制作前缺口。通用要求是按任务的真实使用组件规划，不是所有图标必须采用圆底、名称板或同一坐标。只读历史审核继续用review；新增和修改必须使用生产计划schema_version=2。旧生产记录可读，但不能拿它继续发起新制作或倒填历史。

## 操作顺序

1. 读取项目已确认布局与真实组件PNG。布局必须列出组件版本、宽高、位置、z层级、裁切方式和完整组件范围。当前程序支持120px图层、UI零额外偏移、无裁切的静态RGBA组件；复杂裁切、其他接入方式先解决真实布局支持，不能用假资源或空组件绕过。多状态逐项提供layouts；第一项为本次输出的主布局。
2. 在生产计划每项和JSON控制卡中写入同一份`composition`，字段见[模板](../templates/composition-plan.example.json)。`basis`绑定实际使用依据；framed绑定实际frame/nameplate组件ID；standalone须明确真实使用没有这些组件，布局components为空。独立图标不能虚构圆底，带底框任务不能冒称独立图标。
3. 以120px图层坐标规划`subject_bounds`和`critical_regions`，说明主体摆放、关键识别面与遮挡策略。矩形采用左上闭、右下开。默认保护整个主体范围；确有设计依据允许非关键部分被遮挡时，显式设置allow_noncritical_overlap=true，并逐项保护关键识别面。脚本按真实前景alpha检查声明区域，不从名称板矩形猜测遮挡，也不替代语义与美感判断。
4. 运行`composition_preflight.py`生成规划图，真实组件叠加青色主体范围与紫色识别区；它只是示意图，不是图标。实际查看后填写review，绑定board的绝对路径及SHA-256。规划图必须能由当前资源与区域逐像素重现；只改hash不能放行过期图。没有真实尺寸或资源时，先补已有资料，关键缺口仍在才询问，不以示例或暂定布局进入制作。
5. 计划每项另有`brief`和原有配色、参考分工、generation_inputs。执行start，再执行prepare-request。后者生成可直接传入image_gen.imagegen的arguments：brief、由规划自动追加的构图约束、原输入图加规划图、透明背景。实际图像总数最多3张，包含规划图；原正式style/color参考仍至少1张，十参考审阅基准保持不变。
6. 必须按准备的arguments调用图像工具，不手动省略规划图。更换布局、主体范围、输入或brief时，生成前另存计划、控制卡、规划图并重新start。真实调用回执为JSON，保留arguments及真实返回信息；calls同时绑定request、arguments、receipt和输出。原有inputs仍记录generation_inputs，隐含追加的规划图在arguments内核对。脚本核对请求准备时间、原start、计划与参数一致性；本地回执不是独立后端证明。
7. 生成后按既有流程导出、实际组合看图、文件检查、两遍审核。清单主布局须与制作前第一布局相同。生成有规划不等于像素符合；不能把试制自动转正或事后移动预览掩盖问题。其他状态也需实际组合复查。

```text
python -B scripts/composition_preflight.py /task/inputs/composition.json --output /task/boards/planning.png
# 实际看图；补board描述和review，再把composition同步到计划及JSON控制卡
python -B scripts/review_workflow.py start /task/inputs/design-plan.json --output /task/workflow/01-plan.json --actor maker
python -B scripts/review_workflow.py prepare-request /task/workflow/01-plan.json --item-id 01 --output /task/requests/01.json --actor maker
# 按请求文件arguments调用图像工具；后续record generated等命令沿用固定工作流
```

Windows固定入口：`-Operation composition-plan`映射规划图工具，`-Operation workflow -Arguments @('prepare-request',...)`准备调用，`-Operation composition-case`只读重放随附真实案例。inputs、boards、workflow、requests、records使用同级目录；输出不得覆盖证据或写入证据所在目录的子目录。

## 验证与边界

见[真实试制报告](composition-preflight-validation.md)。验证后才引入本页通用流程。程序能阻断使用本工作流时的缺项和参数不一致，不能从软件层拦截任意直接调用imagegen，也不能证明人工观察或填写的使用依据是真实的。未执行检查或绕过准备参数的制作，不得宣称符合此流程。

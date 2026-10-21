# 用途、层级、轮廓与材质

用于新设计计划和新复查。这里的用途分支与迁移方法是**候选方法，效果未验证**；引用的既有图标仍按原确认范围使用。运行工具或填满表格不证明新方法改善了作品。清雅、柔和是本项目基调，不是所有女性向古风游戏的共同定义。

## 先选用途，再选形式

| 分支 / 代码 | 设计重点 | 可借鉴的结构与材质 | 应避免的误用 |
|---|---|---|---|
| 日常经营 / daily | 操作或产物直接可辨，主体明确 | 器皿、工具、植物；连续亮面与大暗面 | 每个入口都加花、金边或奖励盒 |
| 雅集收藏 / collection | 收藏对象、整理关系、薄厚和秩序 | 纸册、单纸、薄卡、成组藏品 | 用同一盒袋换颜色表示所有功能 |
| 节庆礼遇 / celebration | 展开关系、礼遇层级与集中焦点 | 闭合礼盒或开箱；明暗和色彩可更鲜明 | 把满屏金属反光当高级；日常功能全部仪式化 |
| 叙事往来 / narrative | 传递、连接、相对体量与姿态 | 书信、人物、生命主体 | 自动变成恋爱、幼态或粉色 |
| 自定义 / custom | 上述分类不适合时说明任务依据 | 由功能决定 | 为满足枚举而强行归类 |

分支不预置色相、饱和度比例或固定物件。用同一套描边、左上受光和概括尺度维持画风；用途可以共享材质，也可以采用不同构图。复查旧图只记录当前特征与适用范围，不据新分支重绘。

## 明暗和色彩层级

每枚确定五项：最大/主要亮面、最暗锚点、最高彩度焦点、冷暖关系、第一眼到第二眼的阅读顺序。允许并列或同色，但要明确位置与理由。主色名称不能代替这些关系。

先看120px主体大块和暗部连接，再看色相与装饰。亮面不等于纯白，暗锚不等于黑描边，最高彩度不一定放在最大物体。不要为了柔和把所有材质压灰，也不设未校准的亮度、面积、色数合格阈值。

在八项审核的 `palette.design_checks.value_chroma` 记录实际位置和关系；与计划不一致时判断是否破坏功能/保持项，说明依据，不靠“颜色丰富”判通过。

## 从现有像素中选择范例

下表链接为已有正式参考，未新画示意、未改变资产。实际打开相应完整图和局部图；选入本次十参考后，`materials[].example_ids` 才可引用其ID，绑定仍用原参考文件SHA-256。

| 范例 | 轮廓或材质观察点 | 迁移边界 |
|---|---|---|
| [R16 单纸合约](../assets/flower-contract-v5.png) | 单一近矩形外轮廓、轻倾平面、纸面大亮块，朱印集中 | 不是所有纸张都要加朱印；平面纸张无需硬改成立体箱体视角 |
| [R01 纸册](../assets/album.png) / [纸层局部](../assets/details/album.png) | 纸页厚度、装订和遮挡形成层次，外线与装饰边分开 | 青绿、白花、金边均非必带；与单纸的外轮廓不同 |
| [R02 瓷杯与茶](../assets/tea.png) / [局部](../assets/details/tea.png) | 碗口椭圆、杯碟叠放、连续反光和茶面分区 | 不能让纸、丝绸也出现相同瓷器反光 |
| [R04 丝绸礼盒](../assets/gift.png) / [折面局部](../assets/details/gift.png) | 实心盒体和蝴蝶结弧线；丝带按折面转明暗 | 不把蝴蝶结、紫色或方盒作为系列必需物 |
| [R03 金色银杏](../assets/ginkgo.png) / [叶片局部](../assets/details/ginkgo.png) | 金色是主体色；扇叶主褶、疏朗外轮廓、大亮暗转折 | 金色主体并不等于所有表面强金属反射；不向全组扩散金色 |
| [R11 节日礼盒](../assets/holiday-gift.png) | 红色主体与金色边饰分工；高窄轮廓 | 红金、纹样与比例仅在任务有依据时迁移 |
| [R18 培育道具](../assets/cultivation-fund-v5.png) | 壶、袋、盘分组；透明/软袋/托盘不能共享一套反光 | 本图接受的柔和紫蓝不能推广为所有材料更灰 |
| [R09 青鸟](../assets/bluebird.png) / [羽片局部](../assets/details/bluebird.png) | 羽片成组、翅身连接、生命主体姿态 | 解剖与轮廓优先，不机械套三分之四器皿视角 |

先比较外轮廓类别：`flat`平面纸卡、`vessel`器皿或实心容器、`open_group`展开组合、`living`生命主体、`custom`其他。检查主物轮廓和负形是否可读，不能只靠换主色区分不同功能。相同轮廓可因同系列身份保留；不机械要求每枚形状唯一。

木、竹、陶、漆等可按任务提出，但当前表格没有同等确认的专属范例。`example_ids:[]`，在 `transfer_limit` 写明缺少同材质样本及借鉴范围，仍可制作候选；不能编造R编号或写成已验证材质库。

## 金色与视角规则

- 金色角色：`none`无、`body_color`主体色、`ornament`描金装饰、`metal`金属部件、`mixed`多角色。按物体逐项解释；不设“金色只能点缀”，也不要求每枚都含香槟金。
- 金色叶片/颜料可按大面塑形；金属的连续反光依据曲面；描金是装饰边，不自动替代结构描边。无金色时记录无即可。
- 视角：`front`正面、`slight_tilt`轻倾、`three_quarter`三分之四、`anatomy`依生命结构、`custom`自定。立体容器可优先轻俯三分之四；薄纸卡优先语义清楚的正面或轻倾，不能把器物默认强加给平面物。不同视角仍须内部透视和遮挡自洽。

## 与现有 UI 技能衔接

任务有整体风格依据时，读取已安装 `design-guofeng-flower-game-ui` 的 `references/project-decisions.md`，按需读 `references/reference-atmosphere-families.md` 和 `references/design-direction.md`。优先级仍为本次用户要求、已确认原图、已确认项目决定、候选方法。

映射仅用于用途与视觉语言：日常经营可结合晴和园居/温润工坊；雅集收藏可结合清雅研习；节庆礼遇可结合任务的庆典或暮色氛围；叙事往来可结合人物来访。不是自动绑定，页面的T1–T6剧场也不直接变成图标构图。只迁移明确的冷暖关系、明暗焦点、材质秩序和精度差；不迁入场景背景、文字、底板、人物题材或整套配色。

可在计划 `ui_bridge` 写 `basis/adopt/exclude`；用到源文件时附 `sources:[{path,sha256}]`，校验会绑定其版本。未使用UI技能时可省略整个字段，图标流程独立执行。**实际UI、相邻入口、红点遮挡不属于本技能审核要求，不需要提供或补验，也不计缺项。** 保留固定浅/深底120px与本批图标关系检查。

## 可执行计划与审核

原计划格式在[固定流程](palette-workflow.md)，现使用 `schema_version:2`，每枚增加 `design_language`。现有v1历史文件不改写；需要新复查时输出新计划。

```text
python -B scripts/design_language.py draft /task/inputs/base-plan.json --output /task/inputs/choices.json
# 按本次任务填choices；空模板没有默认配色、分支或通过结论。
python -B scripts/design_language.py prepare /task/inputs/base-plan.json --choices /task/inputs/choices.json --output-dir /task/prepared
python -B scripts/review_workflow.py start /task/prepared/design-plan.json --output /task/records/01-plan.json --actor maker
```

Windows对应 `-Operation design-language -Arguments @('draft', ...)` / `@('prepare', ...)`。prepare核对完整性、选定范例和实际文件哈希，生成新计划、可读简报、未验证审核模板；不自动填入观察或通过。旧控制卡与参考描述继续保留，清单需绑定新计划。

字段：`purpose{branch,reason}`；`hierarchy{lightest,darkest,chroma_focus,temperature,focal_order}`；`shape{family,silhouette,perspective,reason}`；`materials[{subject,material,behavior,example_ids,transfer_limit}]`；`gold{role,reason}`；`method_validation:"unverified"`。可选 `ui_bridge` 如上。

将生成模板按图ID合入首遍和第二遍已有八项的对应项，不覆盖其他观察：

| 现有维度 | design_checks中的检查键 |
|---|---|
| semantics | purpose |
| structure | silhouette、perspective |
| materials | material_behavior、gold_role |
| palette | value_chroma |

每个子项仍为 `{status:pass|fail|unverified, observation:实际观察, location:位置}`。缺子项、缺观察、未验证或失败都不能完整通过；同一维度的总状态不能盖过子项。审核仍只有原有两遍，不建立第二套流程。

`delivery.design_method_effectiveness`保持`unverified`，与资源审核分开。跨用途方法的实际效果只能由后续真实新作与反馈研究支持；当前工具不提供把方法升级为通过的开关。

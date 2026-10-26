# 时装系统：圆底适配v1确认与入库

> **2026-10-26当前状态：R40已替换为用户确认的时装店铺左移2px版，见[准确版本](accepted-r40-storefront-left2-v4.md)。旧R40绣袋继续作废；R39装扮及其原文件保持不变。下文2026-10-23记录保留历史。**

2026-10-23用户明确要求“将调整后的登记为通过，并加入到图库”。本次绑定上一轮交付的fashion-fit-20261022-v1，登记为用户确认通过、正式限定用途参考R39–R40；不批准早期居中稿或其他候选。

| ID | 功能 | 主要用途 | 限制 |
|---|---|---|---|
| R39 | 装扮 | 衣架悬挂衣裙、丝绸垂坠及完整组件避让 | 本案配色、缩放和PNG上移定位不推广；具体换装操作配名称 |
| R40旧绣袋（已作废） | 时装商店历史版本 | 仅供追溯 | 当前有效图见[accepted-r40-storefront-left2-v4](accepted-r40-storefront-left2-v4.md) |

四份高清/120透明PNG从已交付调整稿逐字节复制，没有重绘、重新导出或补色彩标签。准确路径、SHA-256、原来源逻辑名称和包围框见[绑定清单](accepted-fashion-icons.json)。两枚120均由定位后完整1024以LANCZOS派生，入库时再次只读复验像素关联。

组合固定圆底113×113@(4,7)、名称板131×40@(-6,90)、图标120×120@(0,0)，层级圆底→图标→名称板→文字。图案已经统一等比缩至约90.8%，定位写入PNG，UI额外补偿为0。此前实际静态组合检查及几何重放通过，两枚裁出非零alpha和与名称板非零alpha重叠均为0；本次登记用户接受，不冒称新一轮视觉审核。

[界面底色前后组合](../assets/qa/fashion-accepted/composition-before-after.png) · [浅底组合](../assets/qa/fashion-accepted/composition-light.png) · [深底组合](../assets/qa/fashion-accepted/composition-dark.png) · [十参考浅底](../assets/qa/fashion-accepted/ten-reference-light.png) · [十参考深底](../assets/qa/fashion-accepted/ten-reference-dark.png)。前后图中旧稿仅作历史比较，正式参考是调整后列。

**定位与技术边界**：这两张正式参考已为本案UI向上定位，默认四边102px安全区检查失败保留，任务布局边界例外通过。不要为满足通用安全区重新居中、紧裁或改回旧稿，也不要将本案90.8%和位移复制为其他入口默认值。字体与底色仍是预览近似；色彩来源、完整资源交付关卡、引擎/图集压缩/真机未验证。用户确认通过不把历史delivery.status=unverified改写为pass。

公开记录中的external-evidence是外部证据逻辑名称，完整本机可执行记录另存；哈希用于追溯，不代表这些外部文件已经包含在仓库。入库不改变全局设计规范。

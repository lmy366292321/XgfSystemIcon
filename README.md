# XgfSystemIcon

新国风女性向游戏入口图标设计技能。

## 调用

技能名：`design-guofeng-system-icons`。

```text
使用 $design-guofeng-system-icons，设计“好友拜访”入口图标，沿用现有风格和规格，完成120px验收。
```

支持新增功能、现有图标精修及规格检查。默认1024×1024透明PNG、102px安全留白、左上受光和统一描边观感；只做120px小尺寸验收。实际能力依赖调用环境是否提供图像生成/编辑工具。

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

## 在其他设备使用

克隆本仓库，将 `skills/design-guofeng-system-icons` **整个文件夹**复制到对应客户端的技能目录，保留references、assets、scripts、agents结构。不要只复制SKILL.md。安装位置遵循所用客户端的说明；刷新技能列表或开启新会话后检查是否可发现。

GitHub存放文件不等于所有设备已经安装。当前Work技能副本与GitHub维护源需显式同步，不是自动双向同步；修改先核对版本，避免覆盖另一端修改。

## 验收边界

文件规格可自动测量；光源、功能识别、视觉重量、描边与噪点需实际查看120px浅深底对照。引擎导入、图集压缩及真机验收未执行时，不能声称上线通过。

本仓库未添加通用开源许可；参考资源的使用权限由项目所有者决定。

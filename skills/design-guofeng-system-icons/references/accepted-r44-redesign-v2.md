# R44礼包重设计V2：确认及版本替代

2026-10-26用户明确“通过并加入图库，同步GitHub”，确认上一轮交付ranking-shop-gift-redesign-20261026-v2。R44编号沿用，有效资产替换为本次竖式圆角闭合红礼匣、贴面米金宽带、绿花封饰与短尾；旧低矮横匣gift-pack-shop-v5继续作废，保留原文件及历史确认，不复活旧稿、不新增R编号。

[1024透明PNG](../assets/gift-pack-shop-redesign-v2.png) · [120透明PNG](../assets/previews/gift-pack-shop-redesign-v2-120.png) · [文件哈希与确认范围](accepted-r44-redesign-v2.json)。两份PNG从本次明确确认的交付文件逐字节复制，未重绘、改色、重新导出或移动位置；完整最终1024经LANCZOS得到120，入库时再次逐像素复验。

[当前同组组合](../assets/qa/r44-redesign-v2-accepted/composition.png) · [浅底](../assets/qa/r44-redesign-v2-accepted/composition-light.png) · [深底](../assets/qa/r44-redesign-v2-accepted/composition-dark.png) · [旧新对照](../assets/qa/r44-redesign-v2-accepted/old-new-comparison.png) · [固定十参考浅底](../assets/qa/r44-redesign-v2-accepted/ten-reference-light.png) · [深底](../assets/qa/r44-redesign-v2-accepted/ten-reference-dark.png)。旧新对照上排旧R44仅供历史追溯，下排是本次确认版本，其余四枚不变。

仅借鉴本图的闭合匣结构、宽带与封饰主次、柔和色块及圆底适配，不把红/米金/绿、圆角程度、斜角、比例和位移推广为全局规则；具体礼包售卖内容仍依名称。圆底113×113@(4,7)、名称板131×40@(-6,90)，图标120×120，UI额外补偿0。仅少量盒底与短尾在板后，封饰、盖顶和主脸可见；字体/底色为预览近似。

**技术边界继续保留**：默认102px留白诊断与本图任务几何边界例外分别记录，源色彩空间/引擎/图集压缩/真机未验证。此前固定十参考中的R41/R45定位稿被当前工具按默认安全区检查，context失败，最终历史check_batch退出1、delivery.status=fail；本次不改写成通过。用户接受pass、正式参考身份与完整技术交付是不同状态。公开external-evidence为本机证据逻辑名称，不声称全部私有工具记录已纳入仓库。

# 好友底栏：PNG留白定位与最终文件（2026-10-21）

本案参数只适用于这组好友底栏，不是普通图标的统一位移值。普通任务遵循[完整组合输出流程](composition-layout.md)：组合位置写入PNG留白，UI额外补偿归零。准确源文件、最终六份PNG、完整SHA-256及检查记录见[本案JSON](bottom-tab-20261021.json)。原记录形成阶段仅同步本机技能；本公开版已脱敏本机路径，保留版本、哈希和技术边界。图片、ZIP及外部证据未随本次公开版上传。

## 当前使用布局

120是图标图层尺寸。原点为组件120基准框左上角，x向右、y向下，单位为预览1倍CSS像素；不是从缩放截图推定的引擎坐标。

| 图层 | 尺寸 | 当前位置(x,y) |
|---|---|---|
| 图标PNG | 120×120 | (0,0)，缩放1；图内已上移6px |
| 圆框 | 113×113 | (3.5,7) |
| 名称板 | 131×40 | (-5.5,90) |

层级为圆框→图标→名称板→文字，不裁切，三枚共用配置。圆框仍用common_tab_function_2_1.png，名称板仍用common_tab_function_name_1.png；两项资源未合入图标PNG。使用新PNG必须取消旧UI的y=-6补偿；圆框、名称板和组件锚点不归零。

当前图层矩形并集为x[-5.5,125.5]、y[0,130]，即131×130；这不是可见像素包围框。文字仍为预览SimSun 24，底色#877b77是近似；生产字体、选中态和真机未据此核验。

## 最终文件版本

当前交付版本：`bottom-tab-padding-baked-20261021-v1`。
根目录：`external-evidence/output/bottom-tab-padding-baked-20261021-v1/`。以下路径均相对此目录，完整哈希由JSON的current_delivery.exports逐项绑定。

| 图标 | 保留的图案源版本 | 主使用文件（精确120版） | 高清对应稿 |
|---|---|---|---|
| 好友 | friends-v4，图案不动 | 120/friends-padding-120.png | 1024/friends-padding-1024.png |
| 密友 | close-attempt1 | 120/close-padding-120.png | 1024/close-padding-1024.png |
| 好友推荐 | recommendation-attempt1 | 120/recommendation-padding-120.png | 1024/recommendation-padding-1024.png |

全部新PNG只做整数像素平移，没有重绘、缩放或改色。120版从选定的120原文件上移6px，UI补偿为0，是本案组合效果的精确依据。本案v2合同主尺寸为preview，target_translation=[0,-6]，采用nearest-half-away-from-zero：高清理想位移为[0,-51.2]，取整为[0,-51]。1024对应稿从选定高清源上移51px，折算120尺寸为5.9765625px，比目标少0.0234375px；保留区域RGBA原样，未重采样。两种尺寸分别搬移，**新120不是新1024的直接缩小文件**；不要据通用导出规则把它们误记为严格派生一致。

版本记录同时绑定layout.json、底栏PNG留白定位稿.zip、records/02-export-verification.json、03-inspection.json、04-package-verification.json及三张组合对照。SHA-256复核用于确认文件身份，不是新增美术或工程验收。

## 已有验证与限制

- 新对照使用的就是上述最终三枚图案。3枚×3种底色共9组“原120PNG+UI上移6px”与“新120PNG+UI偏移0”逐像素一致，见qa/组合对照-底栏-1x.png及浅底、深底版本。原来“最终推荐稿尚未重新组合核验”的缺口已由这次定位导出对照补齐；不改写之前的历史记录。
- 120版没有裁出任何非透明像素。1024密友稿在固定画布搬移时移出1个alpha=1/255像素，其他高清稿未裁出非透明像素；该事实保留，不改写为“全部像素无损”或另做清噪。
- 原选定PNG、圆框和名称板未覆盖。默认检查仍失败，旧报告保留。2026-10-21检查器适配后，以单独几何合同只读重放：三枚任务边界与两条分支像素均相符；好友、好友推荐几何状态通过，密友因已记录但未明确接受的1个alpha=1像素损失仍为未验证。新120仍不是新1024直接缩小。色彩来源及完整资源交付、引擎验收未升级。
- 新检查位于`external-evidence/validation/layout-rounding-20261021/`，以current_delivery.geometry_validation绑定v2合同、目标/取整结果及哈希；此前v1合同与报告保留在previous_geometry_validation；本轮没有重新导出、补色彩标签、生成对照或重绘。正式图库R24–R27继续绑定[原入库版本](accepted-social-icons.md)，不替换R25/R26或复制派生图入库，图库仍为38张。

## 历史图案选择与布局

用户先要求“密友先保留这版”，随后在截图中选择好友推荐recommendation-attempt1，并表示“我觉得这一个版就可以，不需要继续处理了”。截图与raw/recommendation-attempt1.png、生成回执的关联已在原记录核对；好友图案继续用friends-v4。后续用户另行要求写入PNG留白，形成上述最终定位文件，并明确要求本机技能记录此版本。

早期comparison-bindings.json和bottom-tab-before-after.html使用的是推荐attempt2，只保留为旧对照。recommendation-attempt2、attempt3及bottom-tab-star-precision-20261021-v3试作均不是最终图案。“星星90%、上移8px、右移2px”仍只是中间目标，不是所选图案已实现的实测结论或通用规则。

旧布局是原PNG图层(0,-6)，圆框和名称板坐标同上，补偿尚未写入PNG；旧图层矩形并集为131×136。旧placement.json中的assembly_bounds=(-5.5,0,131,130)只是当时的名义预览区域，不能当作旧全部图层的精确并集。JSON的historical_pre_bake保存原状态和更新前选择记录快照，current_delivery才是现行使用文件依据。external-evidence/与external-resources/是未公开文件的逻辑名称，不是仓库内现成目录。其他设备须经授权取得原文件、建立本机路径映射并核对哈希；不能直接将脱敏案例当作可运行几何合同，也不用重新生成的近似图替代。

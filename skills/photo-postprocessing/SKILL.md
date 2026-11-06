---
name: photo-postprocessing
description: 相机备份照片（DCIM）的后期处理：筛选废片、解 RAW、调色、剪裁、修图、导出可分享作品。当用户上传了新照片、要求挑选/删除废片、把 ARW/HIF 转成 JPG、调色修图或生成分享图时使用。
---

# 照片后期处理

## 环境

- 虚拟环境：`/vol1/@appshare/fn-deepseek-harness/.local/photo-venv`（rawpy、Pillow、numpy、pillow-heif）
- 照片根目录：`/vol1/1000/Photos/Photo/camera/A/DCIM`（可用环境变量 `DSH_PHOTO_DCIM` 覆盖）
- 输出根目录：`/vol1/1000/Photos/Photo/postprocessed`（可用 `DSH_PHOTO_OUT` 覆盖）
- 工具：`$HOME/.agents/skills/photo-postprocessing/scripts/photo.py`
- 环境重建：`sh $HOME/.agents/skills/photo-postprocessing/setup.sh`（幂等）
- 自检：`$HOME/.local/photo-venv/bin/python $HOME/.agents/skills/photo-postprocessing/scripts/selftest.py`
- 其他可用命令：`exiftool`、`ffmpeg`

调用方式（下文用 `PHOTO` 代指）：

```bash
PHOTO="$HOME/.local/photo-venv/bin/python $HOME/.agents/skills/photo-postprocessing/scripts/photo.py"
```

相机为 Sony A7 IV（ILCE-7M4）：4255 个 `.ARW`、639 个 `.HIF`、372 个 `.JPG`，按日期分在 63 个目录里，合计约 132 GB。

## 铁律

1. 原片只读：绝不移动、重命名、删除 DCIM 里的文件；输出只写到 `postprocessed/`。
2. 删片必须由用户确认：先出报告和接触表，用户点头后才谈删除；本工具不提供删除命令。
3. 每个输出 JPG 旁边写同名 `.json` sidecar，记录调色参数和来源文件，便于复现。
4. 默认导出前剥离 GPS，保留相机制造商和镜头信息；用户要求时用 `--keep-gps`。
5. 大目录批量任务用后台作业跑，不要前台阻塞；单张 RAW 约 8 秒。

## 1. 清点

```bash
$PHOTO inventory                     # 文件类型、数量、总大小
$PHOTO inventory --by-folder         # 每个日期目录数量
$PHOTO inventory --folders 11841020  # 只看某个日期目录
```

## 2. 筛选废片

```bash
$PHOTO cull --folders <日期目录> --jobs 3 --sheet --sheet-cols 6
```

- 默认输出到 `postprocessed/_cull/<时间戳>/`：`cull_report.json`、`cull_report.csv`，加了 `--sheet` 时还有 `rejects.jpg` 接触表。
- 指标：清晰度（拉普拉斯方差，与同批中位数比较）、平均亮度、死黑/过曝比例、256 位 dHash 近似重复。
- 标记：`blurry`（明显虚）、`dark`、`bright`、`blown`（高光溢出 >8%）、`crushed`（暗部压死 >35%）、`duplicate`（同目录近似重复，保留第一张）、`unreadable`。
- 阈值是启发式的，报告只是候选：**把 `rejects.jpg` 发给用户看图确认**，再决定删哪些。批量导入时先跑一个日期目录试水，确认阈值合适再跑全库（全库约 40 分钟）。

## 3. 解 RAW 与调色

```bash
$PHOTO develop <文件.ARW> --out <输出.jpg> \
  --ev 0.3 --warmth 10 --contrast 0.15 --shadows 0.2 --highlights -0.3 \
  --saturation 1.08 --vibrance 0.1 --clarity 0.2 --sharpen 0.5 \
  --crop 0.05 0.0 0.95 1.0 --aspect 1.5 --rotate 0 --flip h \
  --spot "1200,800,40" --long-edge 2048 --quality 92
```

参数（都可省略，省略即不动）：

| 参数 | 范围 | 说明 |
| --- | --- | --- |
| `--ev` | 约 -3..3 | 曝光补偿，线性光下乘 2^ev |
| `--warmth` | -100..100 | 正值偏暖，负值偏冷 |
| `--tint` | -100..100 | 正值偏品红，负值偏绿 |
| `--shadows` / `--highlights` | -1..1 | 提暗部 / 压高光（负值恢复高光） |
| `--contrast` | -1..1 | S 曲线 |
| `--saturation` / `--vibrance` | 1.0 基准 / -1..1 | 饱和度 / 自然饱和度 |
| `--clarity` / `--sharpen` / `--denoise` | 0..1 / 0..3 / 0..1 | 局部对比、锐化、降噪 |
| `--crop L T R B` | 0..1 | 按比例裁剪 |
| `--aspect` | 如 1.5 | 居中裁成 3:2 |
| `--rotate` / `--flip` | 度 / h、v | 旋转、翻转 |
| `--spot x,y,r[,sx,sy]` | 像素 | 仿制图章式修瑕，可重复；省略源点则取右侧 |
| `--long-edge` / `--quality` | 默认 2048 / 92 | 输出长边与 JPEG 质量 |

- 输出默认落在 `postprocessed/<今天日期>/<原名>_edit.jpg`，加 `--suffix` 改后缀。
- 已存在同名文件会拒绝覆盖，确认要覆盖加 `--force`。
- 调色思路：先 `--ev` 定曝光，再用 `--highlights`/`--shadows` 找回过曝和暗部，然后 `--warmth`/`--tint` 定白平衡，最后 `--contrast`/`--saturation`/`--clarity` 出风格；一次只改一两个参数并看结果。
- 没有镜头配置文件校正、没有 HDR/堆栈合成、没有 AI 修图；修瑕只能克隆附近的干净区域。

## 4. 导出分享作品

```bash
$PHOTO export <已调好的.jpg> --out <分享图.jpg> --long-edge 2048 --quality 90 \
  --border 0.02 --border-color 255 255 255 --watermark "文字"
```

- 分享图：长边 2048、sRGB、JPEG 90，默认剥离 GPS。
- 需要归档级文件时直接从 RAW 出 16 位中间稿：先 `develop` 到 JPEG，再按需 `--quality 100`。

## 5. 接触表

```bash
$PHOTO sheet --folders <日期目录> --limit 36 --cols 6 --out <表格.jpg>
```

给用户快速过片用；带文件名标签。

## 交付约定

- 交回给用户时给：处理后的文件路径、用了哪些参数（sidecar 已记录）、被标记的废片清单。
- 图片通过飞书发送时用 `lark-cli` 发文件/图片消息；单次不超过 100 词说明，细节放 PR 或文件里。
- 批量任务失败或权限异常时，先确认挂载与 ACL（TRIM 卷用 `trimacl`，普通 `setfacl` 无效），再报告。

# TFT-Sniper

macOS 上用于《金铲铲之战》的纯视觉辅助脚本。

它只做 4 件事：

- 监听 `Shift+D`
- 固定等待一段刷新动画时间
- 截取商店文字带并用 Apple Vision 做 OCR
- 命中目标后按手工标定的卡槽中心执行点击

当前实现已经收敛为一条低维护主线：

- 固定等待，不再保留自适应探针等待
- ROI 和点击点位都支持跟随 `com.tencent.jkchess` 窗口移动
- 点击位置使用手工标定的 5 个卡槽中心，而不是 ROI 五等分推算

## 特点

- 纯视觉方案，不读内存、不注入进程
- 依赖少，只用 Quartz、Vision、`pynput`
- 配置简单，核心参数都在 [config.toml](/Users/hh/Workspace/TFT-Sniper/config.toml)
- 支持运行时热重载：`Cmd+Shift+R`

## 环境要求

- macOS
- Python 3.11+
- 已给终端或 Python 授权：
  - 辅助功能
  - 屏幕录制

## 安装

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 配置思路

项目只需要维护三类配置：

- 匹配条件：`target_heroes`、`target_costs`
- 固定等待：`animation_delay`
- 几何信息：`[roi]`、`[window]`、`[click]`

关键字段说明：

| 字段 | 作用 |
| --- | --- |
| `target_heroes` | 目标英雄名单，命中即点击 |
| `target_costs` | 目标价格列表，命中即点击 |
| `animation_delay` | `Shift+D` 后固定等待多久再截图 |
| `debug` | 是否保存调试图并打印 OCR/耗时日志 |
| `[roi]` | 商店名称和价格文字带的截图区域 |
| `[window]` | 是否跟随 `com.tencent.jkchess` 窗口移动 |
| `[click].slot_points` | 5 个卡槽的点击中心点 |
| `[click]` 下的时序参数 | 多张连买时的点击节奏 |

匹配规则是 OR：

- 名字命中就点击
- 价格命中也点击

## 校准

窗口大小固定、只会移动时，推荐使用窗口跟随模式。

先把金铲铲切到非全屏、固定大小窗口，然后运行：

```bash
.venv/bin/python calibrate.py
```

脚本会要求你依次记录 7 个点：

1. 商店文字条左上角
2. 商店文字条右下角
3. 第 1 张卡点击中心
4. 第 2 张卡点击中心
5. 第 3 张卡点击中心
6. 第 4 张卡点击中心
7. 第 5 张卡点击中心

完成后会自动写回 [config.toml](/Users/hh/Workspace/TFT-Sniper/config.toml)。

## 运行

```bash
.venv/bin/python main.py
```

运行后：

- `Shift+D`：执行一次固定等待 + 截图 + OCR + 点击
- `Cmd+Shift+R`：热重载 [config.toml](/Users/hh/Workspace/TFT-Sniper/config.toml)
- `Ctrl+C`：退出

## 调参建议

- 稳定优先：把 `animation_delay` 设到你这台机器上不会截到旧商店的最小值
- 多张连买偶发漏点：优先增大 `inter_click_ms`，其次增大 `hold_ms`
- 点位不准：重新运行 [calibrate.py](/Users/hh/Workspace/TFT-Sniper/calibrate.py)
- 调试完成后把 `debug = false`，减少磁盘写入和日志噪声

## OCR 价格规则

价格只接受 `1~7`。

这是为了处理金币图标带来的常见 OCR 噪声，例如：

- `93 -> 3`
- `51 -> 1`
- `02 -> 2`
- `⑦ -> 7`

如果价格没识别出来，日志会显示 `?金币`，不会再显示负数。

## 项目结构

```
TFT-Sniper/
├── main.py
├── config.toml
├── calibrate.py
├── trigger.py
├── window.py
├── capture.py
├── ocr.py
├── matcher.py
├── action.py
├── permissions.py
├── logger.py
└── requirements.txt
```

各模块职责：

- [main.py](/Users/hh/Workspace/TFT-Sniper/main.py)：主流程调度
- [trigger.py](/Users/hh/Workspace/TFT-Sniper/trigger.py)：全局热键监听
- [window.py](/Users/hh/Workspace/TFT-Sniper/window.py)：窗口定位和相对坐标解算
- [capture.py](/Users/hh/Workspace/TFT-Sniper/capture.py)：Quartz 截图
- [ocr.py](/Users/hh/Workspace/TFT-Sniper/ocr.py)：Vision OCR 和价格解析
- [matcher.py](/Users/hh/Workspace/TFT-Sniper/matcher.py)：命中判断
- [action.py](/Users/hh/Workspace/TFT-Sniper/action.py)：批量点击
- [calibrate.py](/Users/hh/Workspace/TFT-Sniper/calibrate.py)：ROI 和点击点位校准

## 当前边界

- 默认假设窗口大小固定，只会移动
- 如果窗口大小改变，建议重新校准，而不是依赖自动缩放
- 日志中的“已点击”表示脚本执行了点击，不代表视觉上已经验证购买成功

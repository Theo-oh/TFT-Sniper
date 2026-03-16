# TFT-Sniper — macOS 金铲铲之战纯视觉辅助抓牌脚本

## 1. 项目概述

基于 Python 的纯视觉、非侵入式游戏辅助脚本。在 macOS 下运行《金铲铲之战》时，监听 `d` 键触发屏幕截图，利用 Apple Vision 框架进行 OCR 识别商店卡牌，匹配预设条件后自动模拟点击购买。

**核心理念:** 零内存注入，纯黑盒视觉操作，极速低延迟。

## 2. 运行环境

- **系统:** macOS (Apple Silicon / M4)
- **屏幕:** Retina Display，截图像素坐标(Pixel)与鼠标逻辑坐标(Point)存在 `2x` 缩放关系
- **语言:** Python 3.14+

## 3. 核心依赖

| 库 | 用途 |
|---|---|
| `mss` | 极速屏幕截图（仅截 ROI 区域，不落盘） |
| `pyobjc-framework-Vision` | 调用 Apple Vision 原生 OCR |
| `pyobjc-framework-Quartz` | CGImage 构建 + Quartz 事件 |
| `pynput` | 全局键盘监听 + 鼠标控制（统一用此库，不引入 pyautogui） |

## 4. 核心工作流

### 4.1 触发与防抖 (Trigger)

- `pynput` 后台线程全局监听键盘
- 检测到 `d` 键按下 → 触发识别流程
- **防抖冷却:** 50ms 内忽略重复触发（激进策略，匹配牌库刷新速度）
- **动画等待:** 触发后阻塞等待 ~180ms（可配置），等卡牌翻转动画播完

### 4.2 精准截图 (Capture)

- **1 个 ROI 覆盖整个商店卡牌行**（5 张卡的名称+价格区域）
- 使用 `mss` 截取该 ROI，保留在内存中，不落盘
- 1 次截图 + 1 次 OCR 调用，延迟最优

### 4.3 OCR 识别 (Recognition)

- 将内存图像转为 `CGImage`
- 构建 `VNRecognizeTextRequest`：
  - 语言：`['zh-Hans', 'zh-Hant']`
  - 识别级别：**`.fast`**（ROI 已裁剪干净，快 3-5 倍，足够准确）
- 获取所有 `VNRecognizedTextObservation`，提取文本 + `boundingBox` 坐标
- **按 boundingBox.origin.x 排序**还原从左到右顺序
- **按 boundingBox.origin.y 区分**名字（上方）和价格（下方）
- 最终解析出 5 组 `(英雄名, 价格)` 数据

### 4.4 匹配与购买 (Action)

**匹配规则（OR 关系，任一命中即购买）：**

1. **按名匹配:** OCR 识别的英雄名在 `TARGET_HEROES` 列表中
2. **按价格匹配:** OCR 识别的价格在 `TARGET_COSTS` 列表中
3. 两项可单独配置或同时配置

**购买流程（对每张命中的卡）：**

1. 根据命中卡牌的 ROI 位置计算中心点击坐标
2. 像素坐标(Pixel) ÷ 2 → 逻辑坐标(Point)
3. 记录当前鼠标位置
4. 瞬间移动到目标坐标 → 左键点击
5. 瞬间移回原位
6. **点击顺序：从右到左**（索引 4→0）

### 4.5 热重载配置 (HotReload)

- 监听 `Command+Shift+R` 组合键，按下后重新加载 `config.json`
- 终端打印 `✅ 配置已重载` 确认
- 零轮询开销，即时生效

## 5. 权限检测模块

启动时主动检测两项 macOS 权限：

1. **屏幕录制权限** — `mss` 截图需要，缺失时截图全黑
2. **辅助功能权限** — `pynput` 键鼠控制需要，缺失时监听无响应

缺失时终端输出明确提示并引导用户到"系统设置 → 隐私与安全性"授权。

## 6. 配置文件 (config.json)

```json
{
  "target_heroes": ["阿狸", "德莱文", "卡萨丁"],
  "target_costs": [5, 7],
  "animation_delay": 0.18,
  "debounce_cooldown": 0.05,
  "recognition_level": "fast",
  "debug": false,
  "roi": { "top": 0, "left": 0, "width": 0, "height": 0 }
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `target_heroes` | `string[]` | 目标英雄名单（空数组=不按名匹配） |
| `target_costs` | `int[]` | 目标价格列表（空数组=不按价格匹配） |
| `animation_delay` | `float` | 动画等待秒数 |
| `debounce_cooldown` | `float` | 按键防抖冷却秒数 |
| `recognition_level` | `string` | `"fast"` 或 `"accurate"` |
| `debug` | `bool` | 调试模式：保存截图、打印 OCR 原文/置信度/耗时 |
| `roi` | `object` | 商店卡牌行的截图区域（像素坐标） |

## 7. 日志与调试

- 正常模式：仅打印 `[命中] 阿狸 (3金币) → 已购买` 等关键事件
- 调试模式 (`debug: true`)：
  - 保存每次截图到磁盘
  - 打印 OCR 原始返回文本 + 置信度
  - 打印各阶段耗时（截图/OCR/匹配/点击）
  - 打印坐标转换细节

## 8. 代码结构

```
TFT-Sniper/
├── main.py          # 入口：权限检测 → 加载配置 → 启动监听
├── config.json      # 运行时配置（热重载目标）
├── capture.py       # mss 截图模块
├── ocr.py           # Vision OCR 模块（CGImage 构建 + 文本解析）
├── matcher.py       # 匹配逻辑（名字/价格 OR 匹配）
├── action.py        # 鼠标控制（坐标转换 + 点击）
├── trigger.py       # 键盘监听 + 防抖 + 热重载
├── permissions.py   # macOS 权限检测
├── logger.py        # 日志与调试输出
└── requirements.txt # 依赖清单
```

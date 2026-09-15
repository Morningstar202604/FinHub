# FinHub 品牌规范 — "Treasury Facade"（财政部立面）

> 品牌隐喻：一座古典财政大厅的正立面 — 三角楣 + 横梁 + 三柱 + 台基，
> 楣孔中一枚金币。企业记账与个人理财，同一套规则（"Your Finance Ministry"）。

## 标识系统

| 资产 | 路径 | 用途 |
| --- | --- | --- |
| Favicon（亮） | `web/public/logo-favicon.svg` / `.png` | 亮色主题浏览器标签 |
| Favicon（暗） | `web/public/logo-favicon-dark.svg` / `.png` | 暗色主题浏览器标签 |
| 站点字标 | `web/public/logo_words.svg` / `.png` | README 顶部、宣传物料 |
| 侧栏标（亮底） | `web/src/assets/img/logo-dark.svg` | 浅色侧栏上的绿描边版本 |
| 侧栏标（暗底） | `web/src/assets/img/logo.svg` | 深色侧栏上的暖白描边版本 |

主题切换由 `ThemeContext` 驱动：`data-theme=light` → `/logo-favicon.svg`，
`dark` → `/logo-favicon-dark.svg`；侧栏按 `theme === 'light' ? logoDark : logoLight` 取图。

## 色板

| 角色 | 值 | 说明 |
| --- | --- | --- |
| 主色 · 央行绿 | `#0F3D2E` | 立面描边、暗色 favicon 底 |
| 强调 · 金币金 | `#C9A227` | 楣孔金币、点睛 |
| 底色 · 瓷白 | `#FDFCF9` | 亮色 favicon 底、文档底 |
| 线条 · 暖白 | `#F2EFE6` | 暗底上的描边 |

## 图标几何（56×56 viewBox，stroke-width 3.2，round caps/joins）

```
三角楣   M10 21.5 L28 8 L46 21.5
金币     circle(28, 16, r=2.8)   # 填充金色，无描边
横梁     M13 25.5 H43
三柱     M18 30 V43 · M28 30 V43 · M38 30 V43
台基     M12 47.5 H44
```

⚠️ 实现注意：开放的三角楣路径必须 `fill="none"`，否则默认填充黑色实心三角。
金币 `stroke="none"`、`fill="#C9A227"`。SVG→PNG 用 `cairosvg`（`output_width` 控制尺寸）。

## 字标排版（logo_words，800×450）

- 图标：`translate(70,105) scale(4.3)`
- "FinHub"：126px / weight 700 / `letter-spacing: -2`
- 标语 "YOUR FINANCE MINISTRY"：23px / `letter-spacing: 4`

## 配套资产

- 截图巡览脚本：`scripts-brand/tour3.mjs`（亮/暗/移动三 pass，sessionStorage 预置
  `finhub_setup_skipped` 跳过 setup gate，`localStorage.theme` 控制主题）
- 行情演示数据：`scripts-brand/seed_market_cache.py`（向 Redis 写入 v5 OHLCV 信封与
  quote 行，供离线环境渲染图表；非生产工具）
- 截图输出：`screenshots/`（`*-dark`、`*-mobile` 后缀对应主题/视口变体）

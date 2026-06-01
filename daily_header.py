#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily_header.py - prints a Chinese reading-guide header for the daily report."""
import sys
from datetime import datetime

stamp = datetime.now().strftime("%Y-%m-%d %H:%M")

guide = f"""==================================================
 每日股票報告  -  {stamp}
==================================================

【點睇呢份報告 - 中文導讀】

呢份係「提示」報告，唔係買賣指令。所有決定同落單由你自己做。
核心 ETF（例如 XEQT）長線揸住，唔喺度擇時；以下監察嘅係你嘅持倉同 AI 衛星股。

關鍵字眼意思：
  - IN  = 該技術策略而家會「持倉」（趨勢向上）
  - OUT = 該技術策略而家會「揸現金」（趨勢未向上）
  - TAKE-PROFIT reached = 已升到你設嘅 +3% 止賺位 -> 考慮減持
  - STOP-LOSS reached   = 已跌到你設嘅 -2% 止蝕位 -> 考慮離場
  - within range        = 仲喺止賺同止蝕之間，未觸發

兩步篩選嘅四個格（基本面 + 技術）：
  - Good co + uptrend = 基本面合格 而且 技術向上 -> 考慮入場時機
  - Good co, WAIT     = 好公司但技術未向上 -> 觀察，等時機
  - Weak co RISING    = 升緊但基本面差 -> 陷阱，小心
  - Skip / ETF        = 唔合格，或者係 ETF（冇公司基本面）

提醒：
  - 訊號唔等於保證。回測一路證明冇策略可靠贏到「買入持有」。
  - 衛星係集中押注 AI 主題，會傾向一齊升跌；用細注 + 止蝕控制風險。
  - 高股息／升勢唔代表「應該買」；數據幫你理解，決定係你做。

（教學資訊，唔係投資建議。）

"""

sys.stdout.write(guide)

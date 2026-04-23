# Nexus System — 每週策略調整報告

**產生時間**：2026-04-23 03:18 UTC
**累計執行次數**：13
**資料來源**：performance.log

---

## 本週判定結果

> **半導體／台股供應鏈 表現領先**

## 互動數據摘要

| 領域 | 平均分數 | 總分 | 文章數 |
|------|---------|------|--------|
| 半導體／台股供應鏈 | 2866.0 | 5732.0 | 2 |
| 長壽科學／運動醫學 | 1171.5 | 2343.0 | 2 |

**計分公式**：`views * 1.0 + clicks * 3.0 + shares * 5.0`

### 關鍵字加權調整

由於 **半導體／台股供應鏈** 表現較佳，系統已為該領域增加以下搜尋關鍵字：

  - `TSMC earnings forecast 2026`
  - `AI chip demand supply chain`

另一領域維持基礎關鍵字不變，確保覆蓋率。

## 表現最佳文章

**半導體／台股供應鏈**

  | 文章 | 分數 |
  |------|------|
  | `tsmc-q1-revenue-beats-estimates` | 3331 |
  | `global-chip-shortage-eases-2026` | 2401 |

**長壽科學／運動醫學**

  | 文章 | 分數 |
  |------|------|
  | `nmn-trial-shows-promising-results` | 1342 |
  | `sports-medicine-peptide-therapy` | 1001 |

---

## 系統自我調整邏輯

1. **數據收集**：讀取 `output/manifest.json`（文章元資料）與 `logs/performance.log`（互動數據）。
2. **分數計算**：依加權公式計算每篇文章的互動分數，再按領域聚合平均。
3. **勝出判定**：若兩領域平均分數差距 >10%，判定表現較佳者為「領先」。
4. **關鍵字調整**：為領先領域注入 2 組額外搜尋關鍵字，增加下次 Scout 掃描的深度。
5. **輸出策略**：更新 `config/strategy.json`，供 Scout 下次執行時讀取。

> 本報告由 Nexus System Architect Agent 自動產生，不含任何人工編輯。

---

*Nexus System &copy; 2026 — 零幻覺政策，所有判斷皆基於可驗證數據。*

# RUPA 本地输出文件指南

本文基于 2026-08-10 clean-room 实际运行生成的目录，不推测尚未出现的文件。

## 最重要的结论

真正作为“受保护数据表”交付给下游的是 `release_data.csv`。在对外发送前，仍需由数据负责人确认本次发布已获授权、账本预算允许、字段和公开主体 ID 符合组织政策。其余文件主要用于解释、校验、复现或内部审计，不应整目录无审查地对外复制。

## 公共 run 中的文件

| 文件 | 实际作用 | 建议范围 |
|---|---|---|
| `release_data.csv` | 受保护的行保持数据；包含公开 roster ID 与配置声明的发布字段 | 经授权后可发布 |
| `manifest.json` | 绑定 `run_id`、随机模式、文件名、大小和 SHA-256；`inspect-run` 用它检查完整性 | 审计/交付时建议附带 |
| `NOTICE.txt` | 标明 reproducibility 或 production 模式，并声明最终线性约束残差可能非零 | 建议随数据附带 |
| `metadata.json` | 软件版本、行数、发布列、随机模式、发布类型与公开输出政策 | 审计材料；分享前复核 |
| `privacy_metrics.json` | 基础 epsilon 组合、适用邻接范围及 RDP 限定说明 | 方法与审计材料 |
| `physical_metrics.json` | 约束预检、`repair_alpha` 及 noisy/projected/interpolated/final 状态的残差汇总 | 方法与审计材料 |
| `governance_metrics.json` | fixed-roster、每主体一行、主体数与校准隔离判定 | 治理审计材料 |
| `run_config.json` | 本次运行的有效公开 schema、边界、类别域、先验、约束和会计配置 | 复现材料；先复核来源文字和路径 |
| `risk_scores.csv` | 由公开/合成校准集得到的字段风险分数；private calibration 时不写入公共 run | 研究诊断，通常不随数据发布 |
| `utility_weights.csv` | 字段效用权重；private calibration 时不写入公共 run | 研究诊断 |
| `epsilon_allocation.csv` | 字段 epsilon 分配；private calibration 时不写入公共 run | 方法复现/审计 |
| `joint_risk.csv` | 可选 joint-NMI 诊断；关闭诊断时不存在 | 研究诊断，不是正式 DP 证明 |
| `utility_metrics.json` | 公共 run 中当前为 withheld 状态，说明原始依赖效用指标未公开 | 可保留作边界证明 |
| `attack_metrics.json` | 公共 CLI 未运行攻击模型的状态说明，不是攻击审计结果 | 可保留，但不要称其为已完成攻击审计 |

production + `disjoint_private` 的实测 run 只有 9 个工件，不包含 `risk_scores.csv`、`utility_weights.csv`、`epsilon_allocation.csv` 和 `joint_risk.csv`。

## 只能内部使用

- `.internal_audit/<run_id>.json`：失败原因、主体重叠计数或生产提交前状态，仅限内部。
- `privacy_ledger.sqlite3`：跨 run 隐私预算和哈希链账本。不得发布、清空或人工改写。
- internal attack audit 的 `attack_audit.json`：Linear、Ridge、KNN、RF、GBDT 和类别推断的聚合诊断。它不是正式 DP 证明。
- 原始 calibration/release 表、敏感目标、noisy/projected/repaired 行级中间表和任何逐行预测。

## 用于审计与复现

审计时至少保留 `manifest.json`、`NOTICE.txt`、`metadata.json`、`privacy_metrics.json`、`physical_metrics.json`、`governance_metrics.json` 和授权记录。复现实验还应保留 `run_config.json`、公开/合成输入、软件版本、源 commit 和随机种子；production 模式没有可公开种子，也不应尝试逐值复现。

## 发布前检查

```powershell
rupa-privacy inspect-run runs/RUN_ID --sensitive-target TARGET
rupa-privacy ledger verify --ledger PATH
```

只有 `inspect-run` 成功、账本状态正确、敏感目标不在 CSV 表头、manifest 哈希全部匹配，并完成组织授权后，才把 `release_data.csv` 视为发布候选。


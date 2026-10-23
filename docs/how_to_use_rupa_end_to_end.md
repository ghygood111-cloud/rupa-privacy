# RUPA 从安装到发布：中英文操作指南

本指南来自 2026-08-10 在 Windows 10、Python 3.9.13 上的真实 clean-room 运行。RUPA 当前定位是 fixed-roster、row-preserving、mixed-type 工业微数据发布研究软件，不是通用匿名化平台或合规认证工具。

## 1. 安装 / Installation

在仓库根目录执行。直接调用虚拟环境中的程序，可避开 Windows PowerShell 的 `Activate.ps1` 执行策略。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade "pip>=23" "setuptools>=68" "wheel>=0.41"
.\.venv\Scripts\python.exe -m pip install ".[test]"
.\.venv\Scripts\rupa-privacy.exe --version
```

Run these commands from the repository root. They do not require activating the virtual environment. Internet access or an approved package mirror is needed when dependencies are not cached.

## 2. 最快速示例 / Five-minute example

```powershell
.\.venv\Scripts\rupa-privacy.exe generate-example --output example_data
.\.venv\Scripts\rupa-privacy.exe validate --calibration example_data/calibration.csv --release example_data/release.csv --config example_data/config.yaml
.\.venv\Scripts\rupa-privacy.exe run --calibration example_data/calibration.csv --release example_data/release.csv --config example_data/config.yaml --output runs --run-id quick_start
.\.venv\Scripts\rupa-privacy.exe inspect-run runs/quick_start --sensitive-target production
```

实测输出为 1000 条发布记录、13 个工件，约束 rank 为 4/4，condition number 为 29.6952。最终受保护表是 `runs/quick_start/release_data.csv`。

The tested quick start produced 1,000 protected rows and a valid manifest. It is a reproducibility demonstration, not a confidential production release.

## 3. 自己的数据要准备什么 / Required user files

至少准备三个文件：

| 文件 | 必须内容 |
|---|---|
| `calibration.csv` | 公开主体 ID、全部发布字段、敏感校准目标 |
| `release.csv` | 同名主体 ID 与全部发布字段；不要包含敏感目标 |
| `config.yaml` | schema、边界、类别域、epsilon、先验、约束、邻接和账本 |

Each ID must be nonmissing and unique within its table. Every released numeric field needs a public bound, and every categorical field needs a complete public domain.

## 4. calibration data

校准表用于估计风险、效用和字段预算。它不是要发布的数据。可用模式包括 synthetic、已确认公开数据，或与发布主体完全不重叠的 `disjoint_private` 数据。若使用 `disjoint_private`，其派生参数只保留在内部。

Calibration data fits risk and utility parameters. It must not be copied into the public run. Private calibration subjects are not automatically covered by the release cohort's DP claim.

## 5. release data

发布表是要经过扰动和后处理的输入。它必须包含配置声明的发布字段与公开 roster ID；敏感目标不应存在。输出保留一行对应一个公开主体，但数值和类别会被 DP 机制改变。

Release data is the table to protect. RUPA is row-preserving, so it does not synthesize a new population or support arbitrary query workloads.

## 6. `privacy_unit_id`

`privacy_unit_id` 是邻接定义中的保护主体键，例如 `enterprise_id` 或 `plant_day_id`。当前要求 roster 公开、每主体恰好一行、表内 ID 唯一且非空。

```yaml
adjacency:
  type: fixed_roster_replace_one
  privacy_unit_id: enterprise_id
  roster_is_public: true
  one_row_per_unit: true
```

## 7. public bounds

每个数值字段必须有独立于待发布秘密记录确定的公开上下界。RUPA 用范围 `upper-lower` 校准 Laplace 敏感度，并把输出裁剪回边界。

```yaml
public_bounds:
  inflow_m3d: [50.0, 220.0]
  total_energy_kwh: [800.0, 3500.0]
```

Do not estimate these bounds from confidential release rows without a separately justified private calibration procedure.

## 8. public categorical domains

每个类别字段必须列出完整公开类别域。未知类别、缺失类别域会失败关闭；即使某类别在当前样本没有出现，也应在公共域中保留。

```yaml
public_categories:
  plant_type: [conventional, membrane]
  shift: [day, night, rotating]
```

## 9. utility prior

`regulatory_prior` 为每个发布字段提供公开、预先确定的效用优先级。它与校准数据熵共同形成效用权重。所有值必须为有限、非负实数，且总和须在绝对容差 `1e-6` 内等于 1；软件不会自动归一化该输入。这样 `utility_alpha` 才能明确表示监管先验与归一化熵权重之间的混合比例。该先验是领域输入，不是法律合规结论。

```yaml
regulatory_prior:
  inflow_m3d: 0.18
  treated_outflow_m3d: 0.25
  plant_type: 0.08
```

## 10. linear constraints

当前只支持公开线性等式 `A x = b`。例如水量平衡 `inflow - treated_outflow - process_loss = 0`：

```yaml
constraints:
  - name: public_water_balance
    type: equality
    provenance: public
    coefficients:
      inflow_m3d: 1.0
      treated_outflow_m3d: -1.0
      process_loss_m3d: -1.0
    rhs: 0.0
    tolerance: 0.01
```

一条约束对应 `A` 的一行，`coefficients` 是该行系数，`rhs` 是 `b`。冗余、冲突、近奇异、非有限、不可行、非等式或非公开约束均被拒绝。

## 11. validate

```powershell
rupa-privacy validate --calibration calibration.csv --release release.csv --config config.yaml
```

成功输出包含 calibration/release 行数、发布字段数、约束 PASS/FAIL、rank 和 condition number。始终先验证再运行。

## 12. reproducibility mode

用于合成数据、公开示例和论文复现：

```yaml
privacy:
  randomness_mode: reproducibility
  random_seed: 20260804
  release_data_mode: synthetic
```

相同输入与 seed 的两次实测 release SHA-256 完全相同。公开 NOTICE 会写明 `not for confidential data release`。

## 13. production mode

仅在组织授权的 fixed-roster 发布流程中使用：

```yaml
privacy:
  randomness_mode: production
  random_seed: null
  calibration_mode: disjoint_private
  release_data_mode: confidential
privacy_accounting:
  dataset_id: authorized_dataset_version
  maximum_cumulative_epsilon: 10.0
  ledger_path: privacy_ledger.sqlite3
```

Production 使用操作系统随机源，拒绝固定 seed，公共输出不含 seed。同一输入的两次合法实测 release hash 不同。

This is a production-workflow functional test using non-sensitive demonstration data; it is not a real confidential industrial release.

## 14. ledger

```powershell
rupa-privacy ledger show --ledger privacy_ledger.sqlite3 --dataset-id authorized_dataset_version
rupa-privacy ledger check --ledger privacy_ledger.sqlite3 --dataset-id authorized_dataset_version --maximum-cumulative-epsilon 10 --additional-epsilon 5
rupa-privacy ledger verify --ledger privacy_ledger.sqlite3
```

本轮实测状态为 `0 -> 5 -> projected 10 -> 10 -> projected 15 denied`。超预算运行没有公共输出，也没有增加 released epsilon。不要删除、重命名或人工修改生产账本。

## 15. run

```powershell
rupa-privacy run --calibration calibration.csv --release release.csv --config config.yaml --output runs --run-id release_2026_q3
```

`run_id` 必须唯一。修复后，重复 ID 会被拒绝，但不会删除第一次成功发布的目录。

## 16. inspect

```powershell
rupa-privacy inspect-run runs/release_2026_q3 --sensitive-target production
```

它检查 manifest、工件哈希、`run_id` 一致性、敏感目标、禁止的原始/中间文件和 production seed 泄露。

## 17. 哪个文件可以发布 / What may be released

`release_data.csv` 是数据发布候选；建议同时附 `NOTICE.txt` 和 `manifest.json`。审计 sidecars 是否对外共享由组织政策决定。不要发布 calibration、原始 release、账本、`.internal_audit`、行级中间数据、敏感目标或逐行攻击预测。完整说明见 `docs/local_user_output_guide.md`。

## 18. internal audit

internal attack audit 是经验性泄露诊断，不是正式 DP 证明，也不属于 `rupa-privacy run` 自动功能。它运行 Linear、Ridge、KNN、RF、GBDT 和类别属性推断，结果只能位于 internal 目录。

```powershell
python -m experiments.p1.attack_audit.run
```

该命令要求完整 Git checkout 和 `v0.1.1-p0` 标签。当前 P2-A 工作树包含已验收的约束收口修改，但 runner 仍用 P0 全源码哈希，因此正式 wrapper 在本轮为 PARTIAL。行为门禁通过后，文档化 internal API 已实际运行：best R2 = 0.010713，lowest MAE = 563.237；三个类别 RF accuracy 均低于对应多数类基线。发布目录中没有这些指标。

## 19. 常见错误 / Common failures

| 错误 | 实测结果 | 下一步 |
|---|---|---|
| production 固定 seed | FAIL CLOSED | 设置 `random_seed: null`，不要传 `--seed` |
| calibration/release 主体重叠 | FAIL CLOSED | 使用真正不相交的校准 roster |
| `add_remove` adjacency | FAIL CLOSED | 改为受支持的 `fixed_roster_replace_one`，或换工具 |
| 冗余/病态约束 | FAIL CLOSED | 删除重复行并重新核查公开约束来源 |
| 累计 epsilon 超限 | FAIL CLOSED | 停止发布；只有授权方可重新设计预算 |
| 未知类别 | FAIL CLOSED | 在发布前冻结完整公共类别域 |
| `Activate.ps1` 被阻止 | 安装未激活 | 使用第 1 节直接调用 `.venv\Scripts\python.exe` |

## 20. 完整端到端流程 / End-to-end checklist

```text
准备 calibration.csv + release.csv + config.yaml
-> rupa-privacy validate
-> ledger check（production）
-> rupa-privacy run
-> rupa-privacy inspect-run
-> ledger verify（production）
-> 人工复核 NOTICE/manifest/release_data
-> 组织授权后发布 release_data.csv
```

本轮 water-treatment 场景使用 1500 条 calibration、2000 条 release、9 个数值字段、3 个类别字段和 3 条独立线性等式，无需修改核心源码。第三方复用模拟只修改一个公开数值上界即可再次完成 validate/run/inspect。


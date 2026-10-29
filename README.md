# 相似客户挖掘 · Trade Wind 2.0.0rc2

从客户 CSV/Excel 的产品画像或公司锚点查找相似海外 B2B 公司，输出带来源、评分和待核事项的销售表。在线查询只使用 Trade Wind；不读取或调用原 Apify/Hunter key。内部包内置指定 Trade Wind key，安装时保留 `.credentials/` 隐藏目录。

**发布定位：有边界的内部试用版。** rc2 修复了候选筛选、联系人选择和邮箱验证问题；有自动回归和真实响应回放证据。尚未证明进口商覆盖率、合格采购负责人数量或销售转化优于原版。实际样本与失败案例见 [发布审查](docs/RELEASE_REVIEW.md)，不要只依据测试通过数判断获客效果。

## 安装与运行

Python 3.10+，解压整个 `similar-customer-miner` 文件夹。从任意工作目录运行，以下 `/path/to/skill` 替换为实际安装路径：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r /path/to/skill/requirements.txt
.venv/bin/python /path/to/skill/scripts/verify_package.py
.venv/bin/python /path/to/skill/scripts/tradewind_ops.py doctor
.venv/bin/python /path/to/skill/scripts/run.py --input customers.csv --output preview.json --dry-run
.venv/bin/python /path/to/skill/scripts/run.py --input customers.csv --output leads.xlsx --mode live --max-results 10 --max-credits 2
.venv/bin/python /path/to/skill/scripts/run_report.py leads.xlsx
```

`doctor` 应显示 `config_source: bundled`，不显示 key。默认 `demo` 是离线合成数据，真实任务必须使用 `--mode live`。公开源码不含 key，通过 `TRADEWIND_API_KEY` 或本地 `.env` 配置；明确切换账户才使用 `--env-file`。

## 输入与结果边界

建议至少提供具体英文产品短语，例如 `hand tools / ceramic tiles`。短语内的空格保留；默认每次查询最多 3 个短语、每个种子最多 2 次查询。`hybrid` 可增加公司相似查询；先用 dry-run 查看实际范围。仅有 HS 编码的输入目前不支持发现，需补充产品词或公司锚点。收入、采购额等画像字段不等于供应商支持的搜索条件。

默认要求供应商描述/行业中的产品文本佐证，补全后再次检查国家。缺乏产品佐证的候选保留在证据和统计中，不进入销售页，也不继续补联系人。这是保守筛选，可能遗漏描述不完整或使用同义词的相关公司；`require_product_match: false` 可用于明确的探索任务，结果必须人工复核。纯公司锚点模式没有产品文本可核对，仍是待核候选。

采购/供应链和运营职位优先，企业负责人可作待核备选；HR、营销、编辑、投资者关系及未知职位不作为主联系人。邮箱标为已验证必须满足：响应地址相同、核验不超过 7 天、valid、可投递、catch-all 明确 false。核验状态不证明在职和采购权。

Excel 保持 `线索名单`、`Results`、`Summary` 三页；另外生成 `.stats.json`、`.evidence.json`。核验状态、时间、来源在 Results 中独立保存；候选默认 pending。海关样本数不参与年发货强度评分。空结果也应交付筛除原因，不能自动用 demo 补足。

## 费用和恢复

默认累计本地预算 2 credits、最多补全 5 家。预算不足时保留部分结果；退出码 0=流程结束（可能无候选），1=错误，2=预算/API 状态导致部分交付。未到补全上限不代表全部完成，应看统计。账本按工作目录和账户隔离；重复精确请求在有效期内复用，未知费用停止后续付费调用。预算是客户端预留，不是供应商硬上限。

Trade Wind 内部的 `hunter` 是其数据供应商选择，统一通过 Trade Wind 结算，不需要旧 Hunter key。可选海关仅核验已有公司，不作为 HS 买家发现渠道，也不推断全年采购额。

- [技能执行说明](SKILL.md) · [输入和配置](references/workflow.md)
- [API、费用与恢复](references/tradewind.md) · [工程说明](ENGINEERING.zh-CN.md)
- [升级说明](docs/TRADEWIND_V2.md) · [审查与对比](docs/RELEASE_REVIEW.md)
- [机器可读验证摘要](docs/validation.json) · [包验证](docs/package-validation.json)

## 维护与分发

开发分支 `codex/tradewind-v2`，原版保留在 main。测试：`python -m pytest -q tests`。业务对比用例：`tests/test_business_acceptance.py`，无网络和费用。真实小样本脚本 `scripts/validate_live.py` 必须显式提供累计预算和已有账本，会产生费用。

内部包构建：`python scripts/build_skill.py --output /private/path/skill.zip --key-file /private/path/tradewind.env --recipient sps`。包附逐文件 SHA-256 清单及 ZIP 校验文件，包含本 README、英文说明、SKILL、工程说明和验证结论；排除客户结果、日志、账本和旧凭证。含 key 包仅发给获准使用账户的内部接收者，不上传 GitHub。rc2 替代 rc1，勿混用旧文档或旧安装目录。

历史模块/旧脚本留作回溯和离线测试，不是 v2 在线入口；`scripts/live_smoke.py` 和旧服务价格不适用于本版。

# 相似客户挖掘 · Trade Wind 2.0.0rc1

从高价值客户名单找相似海外 B2B 公司，补充公司资料和候选联系人，输出带来源与评分的销售 Excel。保留原有画像、种子排除、评分与三页表格；在线查询已改为 Trade Wind，不使用原 Apify/Hunter key。

## 安装和使用

解压整个 `similar-customer-miner` 文件夹，包括隐藏目录。Python 3.10+：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r /path/to/similar-customer-miner/requirements.txt
.venv/bin/python /path/to/similar-customer-miner/scripts/tradewind_ops.py doctor
.venv/bin/python /path/to/similar-customer-miner/scripts/run.py --input customers.csv --output leads.xlsx --mode live --max-results 10 --max-credits 2
```

内部包已内置 key，`doctor` 应显示 `config_source: bundled`。公开源码不含 key：开发者通过 `TRADEWIND_API_KEY` 或本地 `.env` 配置。默认模式为离线 demo；真实任务必须加 `--mode live`。仅做预览用 `--dry-run --output preview.json`，不会调用 API。

输出：销售 Excel、费用和状态 `.stats.json`、含完整来源响应的 `.evidence.json`。退出码2代表部分交付，应查看停止原因。账本预算累计计算，缓存请求不再次扣费；超时/计费未知停止后续付费调用。候选联系人和邮箱不自动变成已验证负责人。

- [技能说明](SKILL.md)
- [输入与输出](references/workflow.md)
- [API、海关核验与费用恢复](references/tradewind.md)
- [本次升级与验证](docs/TRADEWIND_V2.md)

Trade Wind 内部可用 Hunter 作为数据源，全部费用通过 Trade Wind 账户结算，没有传入旧 Hunter key。产品词查询是默认发现方式；实测 `similar_to` 可能只返回种子。没有进口证据时保留为空，不用相似度推断中国采购额。

开发验证：`python -m pytest -q`。构建内部包：`python scripts/build_skill.py --output /private/path/skill.zip --key-file /private/path/tradewind.env --recipient internal`。构建只选允许的源文件，排除 `.env`、旧密钥、状态、日志和实测客户数据。内部包带凭证，仅限授权内部同事，不提交 GitHub。

旧实现和测试保留用于回溯；历史 `ENGINEERING*`、`docs/pricing.md` 和旧 `scripts/live_smoke.py` 不适用于v2在线路径，且不随升级包分发。主线保留原版，新版在独立分支迭代。

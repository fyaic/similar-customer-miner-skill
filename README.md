# 相似客户挖掘 · Trade Wind 2.0.0rc4

从客户 CSV/Excel 的产品画像或公司锚点查找相似海外 B2B 公司，输出带来源、评分和待核事项的销售表。在线查询只使用 Trade Wind；不读取或调用原 Apify/Hunter key。内部包内置指定 Trade Wind key，安装时保留 `.credentials/` 隐藏目录。

**使用范围：候选发现与人工复核。** 产品相关性、进口采购身份、联系人任职及采购权需要分别确认；邮箱核验不等于已确认采购联系人。

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

`doctor` 应显示 `config_source: bundled`，不显示 key。执行必须显式指定模式；真实任务使用 `--mode live`，`--mode demo/test` 为离线合成数据。只有 dry-run 可省略模式。公开源码不含 key，通过 `TRADEWIND_API_KEY` 或本地 `.env` 配置；明确切换账户才使用 `--env-file`。

## 输入与结果边界

建议至少提供具体英文产品短语，例如 `hand tools / ceramic tiles`。短语内的空格保留；默认每次查询最多 3 个短语、每个种子最多 2 次查询。`hybrid` 可增加公司相似查询；先用 dry-run 查看实际范围。仅有 HS 编码的输入目前不支持发现，需补充产品词或公司锚点。收入、采购额等画像字段不等于供应商支持的搜索条件。

默认采用三种处置：有产品证据的进入线索名单；证据不足的进入“待复核”，不按无关公司丢弃；明确复核为无关、国家或身份冲突的排除。产品词按完整短语匹配，支持显式 `product_aliases` 同义词配置；无产品词的公司锚点结果仍须人工核实。

需要补足产品证据时，按 [产品复核流程](references/product-review.md) 检查官网产品页，保存带链接、短摘录、核查时间和复核者的 JSON，再使用 `--product-evidence-file reviews.json` 重跑。程序检查证据的公司域名、种子、产品、时效与摘录；不自行抓取官网，也不把文件校验当作官网真实性认证。复用原工作目录、账本和预算；重新入选的公司可能产生新的联系人查询费用。

企业业务角色来自供应商描述，单独列为待核线索；进口证据状态与采购身份分别展示。制造商、零售商或产品相关公司不自动成为已确认进口买家。探索配置 `require_product_match: false` 可保留缺证据候选，但明确复核为无关或身份冲突的仍不入选。

人员默认由 Trade Wind 内部 Apollo 按采购/供应链/运营/负责人职位词检索，每请求一个公司域名，最多补全1人。可通过 people_source、people_job_titles、people_per_page 调整；公司查询仍用 Trade Wind 内部 Hunter。采购/供应链和运营职位优先，企业负责人可作待核备选；HR、营销、编辑、投资者关系及未知职位不作为主联系人。邮箱标为已验证必须满足：响应地址相同、核验不超过 7 天、valid、可投递、catch-all 明确 false，且没有明确不安全标志。safe/role_account 只有可投递和安全发送都为 true 才归一为 valid；原始状态、catch-all 三态与安全发送判断均单独保留。核验状态不证明在职和采购权。

在线 Excel 包含 `线索名单`、`待复核`、`Results`、`Summary` 四页；另外生成 `.stats.json`、`.evidence.json`、`.audit.json` 和 `.review.json`。CSV/Markdown 的待复核候选保存在同名 `.review.json`。核验状态、时间、来源在 Results 中独立保存；候选默认 pending。海关样本数不参与年发货强度评分。空结果也应交付筛除原因，不能自动用 demo 补足。

## 费用和恢复

默认累计本地预算 2 credits、最多补全 5 家。预算不足时保留部分结果；在线退出码 0=范围内全部覆盖且有新增真实业务回执（可以无命中），1=错误，2=部分完成或缺乏真实执行证据。产品待复核、缺域名和补全上限也返回2。显式 --allow-cached 可接受全部阶段有真实历史回执的缓存完成，但不算新增API案例。历史账本没有传输标记的回执为来源未证明，不自动升级成真实执行。账本按工作目录和账户隔离；重复精确请求在有效期内复用，未知费用停止后续付费调用。预算是客户端预留，不是供应商硬上限。

Trade Wind 内部的 `hunter` 是其数据供应商选择，统一通过 Trade Wind 结算，不需要旧 Hunter key。可选海关仅核验已有公司，不作为 HS 买家发现渠道，也不推断全年采购额。

- [技能执行说明](SKILL.md) · [输入和配置](references/workflow.md)
- [API、费用与恢复](references/tradewind.md)

## 执行覆盖核查

正式新任务必须调用 Trade Wind 业务 API；官网研究、健康检查、回放不能替代。每个种子查询与所选候选公司的阶段在 `.audit.json` 可查，区分新增、缓存、待补产品证据和未覆盖。范围是 max-results 内的候选，不代表整个市场。按原账户账本复核：

```bash
python /path/to/skill/scripts/audit_run.py leads.evidence.json --ledger /path/to/account/state.sqlite3
```

账本路径来自运行使用的 state-dir 下账户目录，可用 `tradewind_ops.py usage` 核对。明确接受缓存续跑时加 --allow-cached。核查比较请求、响应与账单状态；它是本地执行核查，不是供应商签名认证。

## 分发与校验

分发包包含本 README、英文说明、SKILL、运行代码、配置、接口参考和输入样例；不包含内部对比评测报告、测试摘要、工程审查文档、客户结果、日志、账本或旧凭证。每个文件的 SHA-256 记录在 `MANIFEST.json`，ZIP 另附 `.sha256` 校验文件。使用 `scripts/verify_package.py` 在本地校验安装文件，无需联网。

内置 key 的包仅发给获准使用账户的接收者，不上传 GitHub。安装时保留 `.credentials/`；rc4 替代 rc3，请解压至新目录，避免混用旧文件。真实任务产生的运行统计和证据用于本次结果复核，不是随包分发的内部评测资料。

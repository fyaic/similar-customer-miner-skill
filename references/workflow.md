# 输入、配置、输出

Python 3.10+。CSV/Excel 支持中英文列名，常用列：`id/客户序号`、`name/客户名`、`main_products/主营商品`、`hs_codes/HS编码`、`region_positioning/客户区域定位`、`industry_leader/行业龙头`、`local_competitors/本土主要竞争对手`、`customer_revenue/客户营业额`、`annual_shipment_frequency/年发货频次`。

产品用具体英文短语，短语之间用 `/ , ; | 、` 分隔，短语内部空格保留。HS-only 输入会在收费前拒绝，需产品词或公司锚点。HS/收入/采购额属于种子画像，不复制为候选事实；不能将“能读入”解释为“均参与在线发现过滤”。在线市场以 `pipeline.target_countries` 的 ISO2 为准，默认美国，不能依赖旧画像中的区域描述覆盖它。

```yaml
pipeline:
  target_countries: [GB]
  max_results_per_customer: 10
tradewind:
  max_credits: '2'
  max_enrich: 3
  discovery_strategy: keywords  # keywords / similar / hybrid
  max_discovery_queries: 2     # 1..4，每次最多3个产品短语；hybrid为锚点预留1次
  require_product_match: true
  product_aliases: {}          # 可配置 faucet: [water taps]，仅用于本地匹配
  contact_search_enabled: true # false仅做公司筛选，不查人员/邮箱
  people_source: hunter        # Trade Wind内部来源；也可apollo/rocketreach
  enrich_people: true
  verify_email: false
  email_verification_mode: quick  # quick / power
```

使用 `--config settings.yaml`，先 `--dry-run` 看实际请求。配置会与默认值合并。超出查询上限的词不自动查询；可调整上限并查看预览。默认保留产品文本已佐证的公司，优先安排有产品证据的公司补全；无佐证的候选进入可见待复核队列，不算明确无关。若改为 false 做探索，未知和未匹配公司也会输出，必须人工筛选；明确复核为无关的仍排除。关键词匹配不证明采购意向、进口身份或真实营业状态，过严也会损失同义词/描述缺失的候选。

补全后国家不匹配或身份冲突隔离。没有国家证据保留空值，不把请求国家当返回事实。人员只选择有匹配公司、个人工作邮箱和采购/运营/企业负责人职位的候选；企业负责人不等于采购负责人。接口最多返回前5个人，只补全最多1个人；这不是穷尽联系人搜索。职位词和邮箱域名不能验证当前任职。

邮箱验证显式开启后，必须匹配响应邮箱，核验时间在过去7天内，valid + deliverable + catch_all=false 才记 verified；未知/缺失状态不通过。Results 独立记录邮箱核验时间、状态、来源。默认 verify_email=false，供应商自报 valid/guessed 都不是独立邮箱核验。quick 可能只返回 valid 而缺少可投递/catch-all字段，按未验证处理；可选 power 做更深检查。两种模式均须满足上述完整条件才标为 verified。

输出：在线 `线索名单`、`待复核`、`Results`、`Summary` 四页 Excel（demo保持三页），另支持 CSV/Markdown；统计 `.stats.json`、原始响应及隔离理由 `.evidence.json`、待复核队列 `.review.json`。CSV/Markdown 同样生成队列 JSON。证据含联系方式，按授权范围保管。A/B/C 衡量字段置信度，事实状态为 pending。`scripts/run_report.py leads.xlsx` 生成 Trade Wind 费用和筛选报告。空结果需解释查询/筛除原因，不生成假线索。

退出码0=流程结束（可能零候选），1=错误，2=预算/API导致部分交付。最多补全N家是上限，不保证处理N家；实际看 enriched_companies 和 enrichment_deferred_count。预算累计包含同账本历史费用与未决预留，缓存精确请求7天；不要换目录绕过未决费用。默认状态位于工作目录 `.similar-state/<账户指纹>`。本版不自动加载旧 local/secrets YAML，内部包默认使用内置 key；明确更换账户才用 `--env-file`。

产品证据复核与同义词的格式、范围和限制见 [产品复核流程](product-review.md)。`business_role` 仅为描述线索；`import_evidence_status` 的 matched_sample 仅代表买家名称/域名匹配的海关样本；`buyer_qualification` 仍为 unverified。

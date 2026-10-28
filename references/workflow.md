# 输入、评分与交付

Python 3.10+。在技能目录创建虚拟环境后安装 requirements.txt，不依赖外部技能或 CLI。

CSV/Excel 支持中英列名：`id/客户序号`、`name/客户名`、`main_products/主营商品`、`hs_codes/HS编码`、`region_positioning/客户区域定位`、`industry_leader/行业龙头`、`local_competitors/本土主要竞争对手`、`annual_shipment_frequency/年发货频次`、`customer_revenue/客户营业额`。最少提供一个产品画像或公司名；建议提供明确英文产品词。

输入的 HS 和收入仅属于种子画像，不能直接复制给候选公司。默认目标市场 US；其他国家在配置的 `pipeline.target_countries` 中用 ISO2（如 GB、DE）覆盖。API 返回缺少国家时保留为空并注明，不能因请求传了 US 就填成已核实美国。

```yaml
pipeline:
  target_countries: [US]
  max_results_per_customer: 10
tradewind:
  max_credits: '2'
  max_enrich: 3
  people_source: hunter
  enrich_people: true
  verify_email: false
```

使用 `--config settings.yaml`。本版不会自动加载旧 `config/local.yaml` 或 `config/secrets.yaml`。`--env-file` 仅用于明确更换 Trade Wind 凭证。私有状态默认位于当前目录 `.similar-state/<账户指纹>`；同一工作目录重复运行会复用请求和累计预算。

输出保持 `线索名单`、`Results`、`Summary` 三页，以及 CSV/Markdown 格式。相似度、适配度、优先级与 A/B/C 字段置信度沿用既有评分。只看评分不能确定公司是进口商，也不能证明联系人在职。`.evidence.json` 含供应商响应和联系方式，仅限任务授权范围保管。

退出码：0 正常完成（可能无匹配）；1 输入/配置错误；2 有部分结果，因预算、API失败或未知状态停止。结果为空不是接口成功证明，也不自动切回演示数据。查询公司名的相似接口本次曾只返回种子，优先用产品词并排除原客户。

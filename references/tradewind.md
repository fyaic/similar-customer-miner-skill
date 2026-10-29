# Trade Wind 接口、费用及恢复

凭证只发给 `https://app.trade-wind.co`，拒绝重定向。无 Apify/Hunter 直连，无 BYOK，无自动收费重试。接口依据：

- [公司搜索](https://docs.trade-wind.co/442720054e0.md)：`company.keywords.include` / `company.names` / `company.domains`；ISO2 位于 `location.country_code`。
- [公司详情](https://docs.trade-wind.co/442720055e0.md)：`identity.domains`；返回 `company.profile`。
- [人员搜索](https://docs.trade-wind.co/442720056e0.md)：`company.domains`；返回 `people`。默认 Apollo，job.job_titles 为采购/供应链/运营/负责人职位词；每次只有一个公司域名，避免跨公司错配。也可配置 Hunter/RocketReach。
- [人员详情](https://docs.trade-wind.co/442720057e0.md)：使用搜索返回的 `source/source_id`，关闭电话解锁。
- [邮箱验证](https://docs.trade-wind.co/442720058e0.md)：`type=single, mode=quick/power`；解析官方 `result`（兼容 `data`），响应邮箱须与请求一致，核验不超过7天；valid、可投递且 `is_catch_all` 明确 false，且无明确不安全标志才标记 verified；safe/role_account 只有可投递和安全发送都为true才归一为valid，原始状态独立保留，仍不证明身份。
- [海关搜索](https://docs.trade-wind.co/447390392e0.md)：根据买家名查询，响应 `records`；二次核对买家名/域名，只合并匹配记录。

费用快照见 `prices.json`（2026-10-27；非合同承诺）：Hunter公司搜索、公司详情、人员搜索/详情各预留0.24 credits；默认Apollo人员搜索/详情各预留0.52 credits（不解锁电话）；单邮箱验证0.1；海关搜索按每行0.14，最少10行预留1.4。实际计费以 `meta.billing` 为准。无结果、超时不等于零费用。

## 海关核验

```bash
python /path/to/skill/scripts/tradewind_ops.py countries
```

从返回的官方参考表选择进口国/出口国 ID，不用 ISO2 猜海关 ID。配置：

```yaml
tradewind:
  customs_enabled: true
  customs_start: '2026-01-01'
  customs_end: '2026-10-28'
  customs_importer_country: '<参考表ID>'
  customs_exporter_country: '<参考表ID>'
  max_credits: '5'
```

仅将完全匹配买家的去重样本记录写入结果；数量标为“样本记录”，不宣称全年发货频次，也不计入发货强度/年频次评分。金额、币种和全年采购额不自动推断。此可选路径的数据可用性取决于账户权限、覆盖范围与实际响应；接口存在不代表目标公司有可用海关记录。

## 账本与恢复

`--max-credits` 是该工作目录下同一账户账本的累计预算，包含过去已确认费用和未决预留。新任务仍复用该账本，勿通过换 state-dir 绕开未决费用。已完成的精确查询7天内复用；未知或失败请求不因缓存过期重新收费。

```bash
python /path/to/skill/scripts/tradewind_ops.py usage
python /path/to/skill/scripts/tradewind_ops.py reconcile <operation-id> --credits <实扣> --state completed --evidence '<服务端回执或日志引用>'
```

对账必须有真实供应商证据，不得猜零或把失败任务强制改为完成。确认失败的请求仍保留，不自动重发。异步 pending 不作为有效结果，本版不自动轮询收费任务。原始状态及 response 留存在权限600的 SQLite/JSON 中。

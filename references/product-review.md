# 产品复核与漏召回恢复

先看“待复核”页或 `.review.json`。候选简介缺少产品词时，不等于企业不经营该产品。优先核查官网产品分类、目录或具体产品页；不使用“产品相关”推断进口、采购规模或人员权限。

## 处置和证据

- `matched` / `matched_alias`：供应商描述有产品短语或显式同义词；仅为文本佐证。
- `reviewed_match`：执行者提供了通过范围校验的官网产品复核记录；保留链接、摘录、时间、复核者。
- `needs_review`：缺少佐证或含糊，进入队列；默认不花联系人补全费用。
- `reviewed_unrelated`：执行者明确复核所有目标产品均无关，排除。网页没找到某个词、403或空简介不足以作负向判断。
- `anchor_only`：没有产品词的公司锚点查询，产品相关性待核。

国家/公司身份冲突优先隔离，正向产品复核不能覆盖冲突。关闭严格产品门槛只适用于探索，不能恢复已明确排除的公司。

## 录入官网复核

使用当前环境的网页读取/浏览能力访问候选自己的官网。研究范围内优先查看最多5家；失败或有歧义就保留待核。记录实际看到的短摘录，不把搜索摘要当完整页面核验。程序本身不抓取官网，不验证摘录是否真实来自该网址；真实性由执行复核的人或代理负责。

将下列**合成示例**改成真实证据，保存在工作目录的 `reviews.json`，不要放入技能安装目录或分发包：

```json
{
  "schema_version": 1,
  "reviews": [{
    "seed_id": "customer-1",
    "domain": "buyer.example",
    "product": "hand tools",
    "decision": "relevant",
    "source_url": "https://buyer.example/products/hand-tools",
    "excerpt": "Professional hand tools for workshops",
    "checked_at": "2026-10-29T09:00:00+08:00",
    "reviewer": "填写实际执行者",
    "reason": "官网产品分类包含目标品类"
  }]
}
```

`seed_id` 必须是本次输入的客户ID；`product` 是其产品短语。HTTPS来源须与候选官网同域（允许www前缀）；跨域母公司目录不自动继承身份。核查时间须带时区、非未来、距执行不超过90天。正向摘录须包含产品或已配置别名。相同种子/域名/产品的重复或冲突记录拒绝加载。负向 decision 为 `unrelated`，必须有明确摘录与理由；不要将信息缺失写为负向。

```bash
python /path/to/skill/scripts/run.py --input customers.csv --output preview.json --product-evidence-file reviews.json --dry-run
python /path/to/skill/scripts/run.py --input customers.csv --output leads.xlsx --product-evidence-file reviews.json --mode live --max-credits 2
```

重跑须保留原 `--config`、结果数量、工作目录和 `--state-dir`（若指定），使查询范围、账户账本和累计预算一致。缓存有效时同请求复用；重新入选公司可能产生新的人员/邮箱查询费用，过期缓存也可能重查。预算不足交付部分结果，不自动扩大预算。仅需要公司筛选时，可在配置中设 `tradewind.contact_search_enabled: false`，此时不查人员和邮箱。

## 显式同义词

例如将目标 `faucet` 与领域内明确等价的 `water taps` 对应：

```yaml
tradewind:
  product_aliases:
    faucet: [water taps]
```

别名只用于本地产品证据匹配，不扩展在线搜索请求。避免单独使用含糊的 `taps` 等多义词；不要把上下游或更宽的品类当作等价同义词。别名匹配结果单独标记为 `matched_alias`。

Excel 的 Results 同时保留企业角色提示、进口证据状态和采购身份。`matched_sample` 仅为匹配买家名称/域名的海关样本，不能证明全年进口额、当前采购需求或目标产品进口；`buyer_qualification` 仍为 `unverified`。

# Similar Value Customer Miner — 数据源付费说明

> 本文档汇总 Skill 可能涉及的外部数据源/服务的成本、门槛和推荐用法，方便你根据预算选择配置。

---

## 一、成本分层概览

| 层级 | 数据源 | 月成本参考 | 适合阶段 |
|------|--------|-----------|---------|
| **L0 免费/零成本** | 内置 demo fallback + 官网爬虫 + 本地规则 | ¥0 | 验证流程、演示、无 API key 时 |
| **L1 低成本** | Apify Free + Hunter Free + OpenCorporates Free | ¥0-300 | 个人小批量测试、月跑 <1000 家公司 |
| **L2 中等成本** | Apify Personal + Hunter Starter/Apollo Basic | ¥300-1500 | 个人/小团队正式使用 |
| **L3 商业级** | ImportGenius / Panjiva / Volza + Apollo Pro/ZoomInfo | ¥3000+ | 团队规模化、需要全球海关数据 |

---

## 二、各服务详细说明

### 2.1 Apify —— ImportYeti 数据入口

**作用**：Apify 是运行 ImportYeti Scraper Actor 的平台。Skill 通过 Apify API 调用 ImportYeti 数据。

**计费模式**：
- 平台本身按 **compute credits** 计费
- 每个 ImportYeti Actor 额外按 **结果数** 收费

**价格参考**（2024-2025 公开信息）：

| 项目 | 价格 |
|------|------|
| Apify Free Plan | 每月约 $5 platform credits，无需信用卡 [Apify Free Plan](https://use-apify.com/docs/what-is-apify/apify-free-plan) |
| Apify Personal Plan | $49/月，含 $49 platform credits [Apify Pricing](https://apify.com/pricing) |
| ImportYeti Actor（结果费） | 约 $2-$30 / 1,000 results，不同 Actor 不同价 [ImportYeti Shipment Data API](https://apify.com/jeeves_is_my_copilot/importyeti-shipment-data-api/api) [ImportYeti Scraper](https://apify.com/parseforge/importyeti-scraper/api) |

**个人使用门槛**：很低。注册 Apify 账号即可拿到 token，Free plan 就能跑小批量。

**省钱建议**：
- 先用 Free plan + 小额 Actor 测试数据质量
- 调低 `max_results_per_customer` 和 `min_shipments` 减少调用量
- 开启本地缓存，避免重复查询

---

### 2.2 Hunter.io —— 邮箱发现与验证

**作用**：根据公司域名发现邮箱 pattern，验证邮箱有效性。

**价格参考**（2024-2025）：

| 套餐 | 价格 | 额度 |
|------|------|------|
| Free | $0 | 25 次搜索/月 + 50 次验证/月 [Hunter Pricing](https://hunter.io/pricing) |
| Starter | $49/月（年付 $34/月） | 500 次搜索 + 1,000 次验证/月 |
| Growth | $149/月 | 2,500 次搜索 + 5,000 次验证/月 |

**个人使用门槛**：很低。Free plan 注册即用，无需商务流程。

**Skill 中使用**：可选。无 Hunter key 时，Skill 会从官网抓取邮箱并用 `info@domain` 模式推断。

---

### 2.3 Apollo.io —— B2B 联系人与公司数据

**作用**：提供公司信息、决策人姓名、职位、邮箱、电话、社媒等。

**价格参考**（2024-2025）：

| 套餐 | 价格 | 额度/特点 |
|------|------|----------|
| Free | $0 | 60 mobile credits/年 + 120 export credits/年，基础搜索 [Apollo Pricing](https://www.bardeen.ai/answers/how-much-is-apollo-io) |
| Basic | $49/人/月 | 更多 credits |
| Professional | $79/人/月 | 高级过滤、序列自动化 |
| Organization | $119/人/月 | API、团队功能 |

**个人使用门槛**：较低。Free plan 可直接注册，付费 plan 在线订阅。API 访问通常需要付费版。

**注意**：Apollo 有 Data Contributor Network，你上传/使用的联系人数据可能被用于丰富它的数据库。对合规敏感的业务需谨慎。[Apollo Review](https://smartreach.io/blog/apollo-io-review/)

---

### 2.4 OpenCorporates —— 公司注册信息核验

**作用**：核验公司注册状态、地址、董事等。

**价格参考**（2024-2025）：

| 层级 | 价格 | 说明 |
|------|------|------|
| Free tier | $0 | 低 rate limit，适合小批量测试 [OpenCorporates Search Actor](https://apify.com/ryanclinton/opencorporates-search) |
| 付费 API | 约 £2,250/年起 | 商业用途、更高额度 [Bellingcat Toolkit](https://bellingcat.gitbook.io/toolkit/more/all-tools/opencorporates) |

**Skill 中使用**：可选。无 token 时跳过核验，仅降低相关字段置信度。

---

### 2.5 ImportGenius / Panjiva / Volza —— 商业海关数据库

**作用**：公司级全球海关进出口记录，包括供应商、采购额、发货频次、产品描述等。

**价格参考**（2024-2025）：

| 服务 | 价格参考 | 覆盖 |
|------|---------|------|
| ImportGenius | $125-$399/月 [ImportGenius Pricing](https://www.softwaresuggest.com/importgenius) | 美国、拉美、部分亚洲国家 |
| Panjiva | 企业级订阅，通常需联系销售 | 全球海关数据 |
| Volza | 订阅制，价格因数据范围而异 | 全球贸易数据 |

**个人使用门槛**：中等偏高。ImportGenius 可在线购买，但月费较高；Panjiva 通常需要商务对接。

**Skill 中定位**：二期扩展数据源。MVP 阶段用 ImportYeti/Apify 即可。

---

## 三、不同使用场景的成本估算

### 场景 A：个人验证 / 月跑 1 次小批量（约 15 家种子客户 → 300 候选公司）

| 服务 | 配置 | 月成本 |
|------|------|--------|
| Apify | Free plan + ImportYeti Actor | $0-$6 |
| Hunter | Free plan | $0 |
| OpenCorporates | Free tier | $0 |
| **合计** | | **约 ¥0-50** |

### 场景 B：个人正式使用 / 月跑 5-10 次（约 1500-3000 候选公司）

| 服务 | 配置 | 月成本 |
|------|------|--------|
| Apify | Personal $49 + Actor 结果费 ~$15 | $64 |
| Hunter | Starter $34/月 | $34 |
| OpenCorporates | Free tier | $0 |
| **合计** | | **约 ¥700** |

### 场景 C：小团队 / 月跑 50 次+ 或需要全球海关数据

| 服务 | 配置 | 月成本 |
|------|------|--------|
| Apify | Team $499 | $499 |
| ImportGenius | Plus ~$199/月 | $199 |
| Apollo | Professional $79/人/月 × 2 | $158 |
| **合计** | | **约 ¥6000+/月** |

---

## 四、推荐配置

### 最低成本验证（推荐先从这里开始）

```yaml
# config/local.yaml
apify:
  api_token: "你的 Apify Free token"
  actor_id: "khadinakbar~importyeti-scraper"

hunter:
  api_key: ""  # 先不填，用官网抓取

opencorporates:
  api_token: ""  # 先不填
```

### 个人正式使用

```yaml
apify:
  api_token: "你的 Apify Personal token"
  actor_id: "khadinakbar~importyeti-scraper"

hunter:
  api_key: "你的 Hunter Starter key"

opencorporates:
  api_token: "你的 OpenCorporates key（可选）"
```

---

## 五、省钱策略

1. **先用 demo fallback 跑通流程**：`apify.api_token` 留空，Skill 会用内置 demo 池，成本为 0。
2. **调小 `max_results_per_customer`**：默认 30，测试时改为 10-20。
3. **开启缓存**：`config/default.yaml` 中 `cache.enabled: true`，避免重复付费调用。
4. **Hunter 和 OpenCorporates 不是必须**：无 key 时 Skill 会降级，仍能输出结构化结果。
5. **批量前先单条测试**：用 `examples/sample_customers.xlsx` 验证 Actor 返回格式和数据质量。

---

## 六、不付费能做什么

即使不配置任何 API key，Skill 也能：

- 解析你的价值客户清单
- 生成客户画像和搜索词
- 输出 30 家美国零售商/分销商候选（demo fallback）
- 补全静态公开社媒链接
- 输出带 citation/confidence/notes 的结构化 Excel

这足够验证流程、培训团队、向领导演示。确认有价值后再逐步配 key。

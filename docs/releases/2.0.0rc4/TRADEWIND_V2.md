# Trade Wind 2.0.0rc4 升级说明

分支 `codex/tradewind-v2-rc4`，基线标签 `v2.0.0rc3`（a6e8439）。main、rc2和rc3引用均保留。

在线只走 Trade Wind，没有旧 Apify/Hunter 直连或 BYOK。rc4新增显式运行模式、逐查询/逐公司覆盖审计、真实传输来源、账本复核及缓存案例分类。产品待核、缺域名、补全上限或回执缺失不再算全部完成。

默认人员数据源是 Trade Wind 内部 Apollo，按采购、供应链、运营和负责人职位词检索，每次仅一个公司域名；公司查询仍为 Hunter。人员邮箱与公司归属分别校验，最多补全1人。邮箱 safe/role_account 有条件归一，保留原始状态和 catch-all 三态。

本轮证据见 RELEASE_REVIEW.md 和 validation.json。rc3 原报告保留于 releases/2.0.0rc3；内部报告不随分发包交付。覆盖审计只证明配置范围内执行过，不证明全市场穷尽、采购权或转化效果。

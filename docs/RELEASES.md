# 版本与交付管理

## 已固定版本

| 版本 | 标签 | 源码提交 | 维护分支 | 说明 |
|---|---|---|---|---|
| 2.0.0rc6 | v2.0.0rc6 | 以标签解析为准 | codex/tradewind-v2-rc6 | 核心阶段优先、邮箱失败结算、费用交接报告 |
| 2.0.0rc5 | v2.0.0rc5 | 以标签解析为准 | codex/tradewind-v2-rc5 | 连接拒绝分类、旧记录恢复、无凭证网络诊断、小样本入口 |
| 2.0.0rc4 | v2.0.0rc4 | 85f3fd22dd6318a98e19b48370c501f731077aee | codex/tradewind-v2-rc4 | 真实业务回执门槛、逐公司覆盖审计、Apollo职位检索、邮箱状态兼容 |
| 2.0.0rc3 | v2.0.0rc3 | a6e84397b42a33f96c5b54913295d08772854ff3 | codex/tradewind-v2-rc3 | 可见复核队列、产品补证恢复、资格字段拆分 |
| 2.0.0rc2 | v2.0.0rc2 | 4d38dfe404e481e9d83cf34d54693d6eaec9cf11 | codex/tradewind-v2 | Trade Wind接入与接收者分发基线 |

main保留原基线52d6904ebe54ea63a98969a5c700cbe3ece296e5。本轮不合并main，不移动既有标签，不覆盖旧ZIP。

当前修复交付版本是rc6，见[本轮审查](RELEASE_REVIEW.md)；下述rc4为历史固定交付记录。具体安装包、校验值、验收结论和使用边界见 [rc4交付记录](DELIVERY_RC4.md)。[本轮审查](RELEASE_REVIEW.md)、[验证摘要](validation.json)、[安装包验证](package-validation.json)与[rc3归档](releases/2.0.0rc3/RELEASE_REVIEW.md)、[rc2归档](releases/2.0.0rc2/RELEASE_REVIEW.md)分别保存。

## 标签、分支与文档的关系

标签固定交付源码，维护分支可以继续接受文档提交。rc4交付后的ff83789提交仅补充仓库工程和交付记录，未修改运行代码、包内README/SKILL或已交付ZIP，因此不提升运行版本，也不重建同名包。接收者追溯以ZIP内MANIFEST.source_revision及v2.0.0rc4为准，不以维护分支最新HEAD替代。

后续若改变运行行为、默认配置、依赖或包内文档，采用新版本、新提交、新标签和新ZIP文件名；禁止在原标签下静默替换交付物。文档维护提交不得把历史测试描述成新执行的测试。

## 发布与回退

运行版本来自src/tradewind_core/__init__.py，发布时同步pyproject、default.yaml、SKILL、双语README、工程说明及当前评测。旧报告按版本归档，不改写成新版本结果。

发布顺序：行为回归和冻结回放 → 必要的有界真实API验证 → 同步文档 → 验证候选包 → 提交推送版本分支 → 创建不可覆盖标签 → 从干净标签提交构建最终ZIP → 解压核对源码提交、哈希、key唯一位置和便携入口 → 更新交付记录。构建前确认HEAD就是预期发布提交；不能从已有后续维护提交的分支直接重建同名发布包。

Git只管理无密钥源码与脱敏摘要。含key包仅保存在本地受限目录，不作为GitHub附件；原始回执、联系人、客户结果和账本保存在忽略目录。分发包排除docs、工程说明、内部评测、测试及客户输出。

回退时解压对应旧版到新目录，保留隐藏.credentials目录；沿用原工作目录和账户账本。禁止通过删除账本、重置预算或更换state-dir绕过费用未决状态。

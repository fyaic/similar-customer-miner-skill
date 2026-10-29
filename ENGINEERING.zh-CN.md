# 工程说明 · Trade Wind 2.0.0rc2

本文件对应 `codex/tradewind-v2`。原架构在 main/Git 历史可查；旧 Apify/Hunter 配置和脚本不再指导新版在线运行。

在线链路为 `parser → profiler → tradewind.mine → scoring → exporter`。CLI 不加载 local/secrets YAML，并清空旧凭证；便携入口为 `scripts/run.py`。demo/test 保留离线旧实现。Trade Wind 客户端、同账户 SQLite 账本、鉴权域名限制、禁止重定向、脱敏和精确缓存复用沿用海外同行项目经验。

发现阶段保留产品短语，限制每个种子的请求数；可选 hybrid 同时使用公司锚点。按域名/名称精确去重，按画像适配度安排有界补全。产品筛选采用供应商描述/行业中的词项匹配，不做同义词扩展，也不证明进口身份；默认将未知/未佐证候选留在证据中。国家补全后复检，冲突隔离，缺失不冒充已核实。跨种子重复公司暂保留首次归属。

联系人采用职位启发式排序：采购/供应链、运营、企业负责人备选。无关或未知职位不写为主联系人；必须匹配公司和个人工作邮箱域名。邮箱验证支持官方 result 和兼容 data 响应，校验同一地址、7天内证据、valid、可投递、catch-all 明确 false；核验来源/时间独立于邮箱发现来源。当前任职和采购权均待核。

评分按实际目标国家计算；海关样本条数不再充当发货强度或年频次。A/B/C 是字段置信度，不是客户质量评级，也不能代替触达前核验。Excel 保持三页布局，增加产品匹配、职位匹配和邮箱核验审计列。运行报告按 Trade Wind 的费用、复用、筛除和未决状态生成。

维护验证：`python -m pytest -q tests`；同一 `tests/test_business_acceptance.py` 在 rc1 和 rc2 分别运行。用例针对已知风险，不是随机市场效果基准。真实脚本 `scripts/validate_live.py` 显式收费，必须复用已有账本并设置累计预算。原始客户响应、邮件地址和 key 不入公共仓库。

版本由 `src/tradewind_core/__init__.py` 供运行与打包引用；发布时同步 pyproject、default.yaml、SKILL、双语 README 和审查记录。包生成逐文件 MANIFEST 与内部 DISTRIBUTION 元数据；在独立安装目录验证入口、配置来源、导出和清单。验收依据见 [发布审查](docs/RELEASE_REVIEW.md) 与 [验证摘要](docs/validation.json)。

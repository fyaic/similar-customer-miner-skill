# 工程说明 · Trade Wind 2.0.0rc6

本文件对应 `codex/tradewind-v2-rc6`。原架构在 main/Git 历史可查；旧 Apify/Hunter 配置和脚本不再指导新版在线运行。

在线链路为 `parser → profiler → tradewind.mine → scoring → exporter`。CLI 不加载 local/secrets YAML，并清空旧凭证；便携入口为 `scripts/run.py`。demo/test 保留离线旧实现。Trade Wind 客户端、同账户 SQLite 账本、鉴权域名限制、禁止重定向、脱敏和精确缓存复用沿用海外同行项目经验。

发现阶段保留产品短语、按种子限额；按域名/名称精确去重。`src/qualification.py` 采用连续词项匹配、显式同义词、否定句保护和种子/域名/产品绑定的复核证据。无匹配只代表 needs_review，不代表无关。官网复核记录需 HTTPS 同域链接、摘录、复核者和90天内带时区时间；记录加载失败在收费前终止。正向摘录须包含产品/别名；多产品公司只有所有目标产品明确负向才排除。程序不自动读取或认证官网内容。

在线输出新增待复核页和私有 `.review.json`，CSV/Markdown也保留队列。已佐证候选优先补全；国家/身份冲突优先隔离，产品正向证据不能覆盖冲突。明确无关的公司不查联系人。`contact_search_enabled: false` 只做公司筛选，不调用人员/邮箱。企业角色仅是供应商描述提示，进口样本与采购身份分开；跨种子归属仍为首次匹配。

联系人采用职位启发式排序：采购/供应链、运营、企业负责人备选。无关或未知职位不写为主联系人；必须匹配公司和个人工作邮箱域名。邮箱验证支持官方 result 和兼容 data 响应，校验同一地址、7天内证据、valid、可投递、catch-all 明确 false且无明确不安全标志；safe/role_account只有可投递与安全发送都为true才归一为valid，导出保留原始状态与布尔三态；核验来源/时间独立于邮箱发现来源。当前任职和采购权均待核。

评分按实际目标国家计算；海关样本条数不再充当发货强度或年频次。A/B/C 是字段置信度，不是客户质量评级，也不能代替触达前核验。在线 Excel 为四页布局，包含待复核页，增加产品匹配、职位匹配和邮箱核验审计列。运行报告按 Trade Wind 的费用、复用、筛除和未决状态生成。

维护验证：`python -m pytest -q tests`；rc6共188项测试通过；旧版本对照结果仅作为对应历史版本记录。用例针对已知风险，不是随机市场效果基准。真实脚本 `scripts/validate_live.py` 显式收费，必须复用已有账本并设置累计预算。原始客户响应、邮件地址和 key 不入公共仓库。

版本由 `src/tradewind_core/__init__.py` 供运行与打包引用；发布时同步 pyproject、default.yaml、SKILL、双语 README 和审查记录。包生成逐文件 MANIFEST 与内部 DISTRIBUTION 元数据；在独立安装目录验证入口、配置来源、导出和清单。验收依据见 [发布审查](docs/RELEASE_REVIEW.md) 与 [验证摘要](docs/validation.json)。

分发策略：`scripts/build_skill.py` 仅包含接收者所需的代码、配置、接口参考、输入样例、README 和 SKILL；排除整个 docs 目录、工程说明、测试及评测脚本。API目录中的 `live_verified`/`live_scope` 内部探测注记仅在打包时移除，接口契约保持不变。内置 key 只写入 `.credentials/tradewind.env`，MANIFEST/DISTRIBUTION 标记 `distribution_profile: recipient`。内部报告留在仓库和本地验收目录，独立管理。运行版号为rc6；rc2至rc5标签与分发包保留不覆盖，旧报告按版本归档于docs/releases。

构建：`python scripts/build_skill.py --output /private/path/skill.zip --key-file /private/path/tradewind.env --recipient sps`。检查包内 Markdown 本地链接、排除清单、凭证唯一位置和独立目录 doctor；不要把验收目录附入交付包。

## rc4执行审计

执行必须显式选择模式；逐种子查询、逐公司阶段检查覆盖。新增真实、缓存、注入回放与旧版来源未证明分别记录。缺域名、产品待核或补全上限均属于未完成；使用audit_run.py与原账本核对请求、响应和费用。默认Apollo职位筛选，每次单公司域名。邮箱状态归一保留原值及catch-all三态。

## 发布身份

见[版本管理](docs/RELEASES.md)与[rc4固定交付记录](docs/DELIVERY_RC4.md)。当前ZIP对应v2.0.0rc6，具体提交由标签及包内MANIFEST解析；rc4历史交付为85f3fd2，不覆盖。运行行为或包内文档变化必须使用新的发布版本。

## rc5 connection incident

Typed urllib connection-refused errors are classified not_sent and release only that attempt's reservation; timeouts/resets remain unknown. No in-call retries. The account ledger preserves prior attempts and opt-in rc4 migration archives originals transactionally in network_recoveries. Network diagnosis uses credential-free HEAD with the same system proxy; direct mode is explicit only. --trial bounds the first seed, discovery query and enrichment. Business output includes .status.md; JSON remains diagnostic evidence. See docs/RELEASE_REVIEW.md for current evidence; rc4 delivery identity remains historical and unchanged.

## rc6 billing workflow

Current delivery: v2.0.0rc6 on codex/tradewind-v2-rc6. Core stages precede mailbox checks. Known terminal email failures are retained without retry; unresolved billing remains blocked. Use billing-report for a redacted local handoff. See docs/RELEASE_REVIEW.md and docs/validation.json for this release; earlier counts refer only to historical releases.

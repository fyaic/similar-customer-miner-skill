# 网络异常诊断与恢复

rc5修复了rc4将连接拒绝混入费用未知、异常来源显示legacy的问题。此流程由执行skill的助手完成，不让业务人员反复查JSON、改代理或猜账单。

## 首次试跑与异常处理

1. 使用运行skill的同一个Python、工作目录及原state-dir。执行 `python /path/to/skill/scripts/tradewind_ops.py diagnose --output network-diagnostics.json`。这是不带Trade Wind key的HEAD网络探测，保持系统代理，只报告代理主机/端口，不输出代理认证信息。获得HTTP状态码只证明路径可达，不证明key、余额或业务接口正常。
2. 若网络不通，停止收费查询，汇总一份中文说明：连接阶段、代理或直连目标、错误类别、是否有HTTP响应。代理端口拒绝时说明所配置代理不可连接；不得武断归因于Trade Wind故障，不说“等状态自动恢复”。不得自动关闭防火墙、修改系统代理或绕过组织网络策略。只有运行环境允许直连且用户/运维明确要求时才用 `diagnose --proxy-mode direct` 和 `run.py --proxy-mode direct`；该参数仅影响这次进程。
3. 对携带旧rc4账本的用户，先运行 `python /path/to/skill/scripts/tradewind_ops.py --state-dir /original/state-root recover-refused`。只有匹配严格的rc4记录（URLError、明确[WinError 10061]、无HTTP响应/返回数据/request_id/task_id、零已确认扣费）才可在已授权故障修复范围内执行同命令加 `--apply`。它保存完整旧记录到network_recoveries表、只释放匹配项的预留；不改预算、账户或其他未决项。无匹配不得用reconcile猜零。
4. 网络可达且旧记录恢复后，用户说“先几条/试跑”必须使用 `run.py --input customers.csv --output trial.xlsx --mode live --trial`，沿用原账本与累计预算。trial只处理首个种子、每次至多3家公司、最多1次发现查询和1家公司补全；用户给更低上限时保留。不能设置per_page=100。候选未全部补全时仍会返回2，这是有意的小样本范围，不冒充完整批次。
5. 给业务侧交付Excel和同名.status.md的中文说明；.audit.json、.evidence.json和诊断JSON供维护留档，不用原始JSON替代业务结果。说明缺少数据是查询失败、未命中还是范围上限，不能混为“没客户”。若网络依然阻断，只一次性说明需要运维恢复的具体路径，不要求业务连续试错。

## 状态边界

- `not_sent`：新请求只有在底层明确连接拒绝（包括Windows 10061）时使用。连接尚未建立，本地预留释放、该次网络尝试的费用记0，依据是连接阶段证据，不伪造供应商账单。不自动重试；后续修复网络后主动重跑可产生新操作。
- `unknown`：超时、连接重置、服务端5xx、非JSON响应、缺计费信息或其他未确认异常仍需保留；不能用网络恢复推断原请求未收费。
- `legacy`：rc4失败路径曾漏写来源，不能据此判断走了旧服务商。旧恢复记录保留来源未证明；新失败明确记录live/injected，仍不能作为成功业务回执。

新版不能替远程电脑修复代理服务或网络策略。诊断和历史恢复不会调用收费API，也不会删除历史账本。每次尝试保留证据；不要通过更换state-dir反复收费试错。

CLI遇到新的明确连接拒绝后，会自动做一次不带凭证的网络检查，将说明附加到.status.md，诊断细节存为.diagnostics.json；无需让业务再发起一次诊断。

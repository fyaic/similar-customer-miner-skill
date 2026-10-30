# 2.0.0rc5 发布审查：Windows连接拒绝

日期：2026-10-30；基线rc4维护提交ff83789；分支codex/tradewind-v2-rc5。原rc4报告归档于releases/2.0.0rc4，分发包不含此报告。

## 确认的问题与责任

业务反馈POST /api/company/search发生URLError / WinError10061，无HTTP状态、request_id和计费回执，0.24本地预留被长期保留，来源显示legacy。代码审查和复现确认两处实现问题：所有传输异常不加区分进入unknown；异常路径未记录transport导致默认legacy。此外“先试几条”缺少专用范围限制。不能将这次故障笼统归咎于供应商，也不能将legacy解释成使用旧Apify/Hunter。

连接拒绝发生在哪个代理/目标端口，现有业务记录没有保留足够证据。我们没有远程Windows机器的访问权限，不声称已修复该电脑代理服务、防火墙或网络配置。当前本机系统代理路径可达，不证明故障发生时远端正常。

## 修复

- 仅URLError.reason为OSError且errno为ECONNREFUSED/10061或winerror10061时判定not_sent；本地预留释放，该次连接未建立费用依据独立于供应商账单。普通错误字符串不自动作为新请求的未发送证明。
- 超时、连接重置、服务端5xx、解析或计费异常仍保留unknown；无自动重试。后续主动运行可以重新尝试not_sent操作，保留旧记录。
- 所有新异常保留live/injected来源与错误阶段，不再错误显示legacy。
- CLI遇到明确连接拒绝后自动执行一次无凭证诊断，输出中文说明和独立.diagnostics.json，不要求业务再手动排查。
- diagnose使用无Trade Wind凭证HEAD检查实际系统代理路径，只暴露代理主机/端口，重定向不跟随。HTTP响应仅证明网络交换。
- recover-refused默认预览；--apply仅匹配rc4保存的明确[WinError 10061]及无HTTP/数据/request_id/task_id、零已确认扣费、原异常notes条件。完整原记录保存在network_recoveries中，事务更新；不动其他未决项、预算和账户。
- --trial限制首个种子、最多3家公司、一次发现和1家公司补全，保留用户更低上限。增加.status.md作为业务侧说明，JSON留作维护证据。

## 验证

169项测试通过，1条既有Pandas警告；新增19项涵盖类型化Windows10061、真实本机关闭端口和关闭代理端口、原生产HTTP传输路径、超时保持预留、无自动重试、旧记录恢复/原文归档/幂等/拒绝误清除、代理认证脱敏、试跑范围限制。真实关闭代理端口经生产Client记为live/not_sent，费用和预留均0。

已安装候选包真实查询业务相同关键词sofas、upholstered furniture、dining tables，国家US，per_page=3。收到HTTP201、request_id=req_Vo7FWjgHuxhY，返回3家公司，实扣0.24 credits。沿用既有账本：14.46→14.70 credits，累计上限16.34，未决0。本轮明确max_enrich=0，仅验证公司搜索，没有验证联系人、邮箱或采购权；3家公司留待复核，退出2，不宣传为完成整批获客。

独立安装校验包括doctor、清单、本地文档链接、原始key仅在凭证文件、报告排除及冻结数据回放。最终干净提交包记录在本地交付说明。新包仍只调用Trade Wind，不用旧服务商key。

## 交付边界

rc5修复已证实的软件错误，提供一次完成的维护诊断流程；不是绕过企业网络策略的工具。业务环境若仍有无监听代理端口，需要恢复该服务，软件不能保证自动恢复外部网络。未获取远端真实SQLite，仅以同结构故障记录验证迁移，不虚称已清理业务电脑账本。保留rc4包和标签以便追溯。

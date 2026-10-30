# Trade Wind 2.0.0rc5 升级说明

分支codex/tradewind-v2-rc5，基线为rc4维护提交ff83789。rc4发布标签及ZIP保持不变。

本轮处理Windows业务试用中的URLError/WinError10061。已确认rc4将明确连接拒绝记为unknown，失败路径漏写传输来源导致显示legacy。rc5只将类型明确的连接拒绝分为not_sent并释放该次预留；超时、重置、5xx及费用未知仍阻断。单次请求不自动重试。

新增不带Trade Wind凭证的diagnose网络探测、严格的旧rc4记录恢复及原记录事务归档；系统代理默认不变，direct必须显式指定。--trial将试跑限制为首个种子、最多3家候选、一次发现和1家公司补全。给业务侧生成.status.md中文说明。

详情见[发布审查](RELEASE_REVIEW.md)、[版本管理](RELEASES.md)、[网络恢复](../references/network-recovery.md)。当前本机真实家具查询通过，不代表远程Windows网络已经修复。

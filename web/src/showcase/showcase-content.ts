export const STACK = ["React", "FastAPI", "LangGraph", "FastMCP", "PostgreSQL", "Docker Compose", "GitHub Actions"] as const;

export const WORKFLOWS = [
  ["01", "库存不足 · 补货", "库存证据 → 策略计算 → 绑定审批 → 幂等补货工单 → 审计回放"],
  ["02", "设备告警 · 维修", "设备状态 → 告警评估 → 绑定审批 → 幂等维修工单 → 审计回放"],
  ["03", "作业阻塞 · 恢复", "任务状态 → 阻塞诊断 → 绑定审批 → 幂等恢复工单 → 审计回放"],
] as const;

export const EVIDENCE = [
  ["非法输入", "严格请求与 JSON 边界，失败时安全关闭。"],
  ["状态恢复", "持久化快照支持进程重启后的确定性恢复。"],
  ["审批竞态", "数据库原子更新确保并发审批只有一个胜者。"],
  ["幂等写入", "相同命令安全重放并返回同一工单。"],
  ["重启恢复", "API、MCP 与数据库中断场景具有自动化回归证据。"],
] as const;

export const LIMITATIONS = ["Mock 模型", "生产 IAM/SSO", "自动部署", "完整浏览器 E2E", "不提供公开可写服务"] as const;

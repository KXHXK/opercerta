# OperCerta 开发日志

本目录是 OperCerta 的可复查工程记录，不是聊天记录备份。

## 阅读顺序

1. 根目录 `DOCUMENT_INDEX.md`
2. `current-state.md`
3. 最近一份 `daily/` 日志
4. 与当前任务相关的 `decisions/` 记录
5. `IMPLEMENTATION_HANDOFF.md`、实施计划和新鲜 Git/测试输出

## 文件职责

- `current-state.md`：只写已验证的当前事实、阻塞、下一步和发布门禁。
- `daily/YYYY-MM-DD.md`：按检查点追加当天的目标、观察、动作、证据、结果和下一步。
- `decisions/YYYY-MM-DD-主题.md`：记录架构、安全、环境、数据模型或发布门禁的稳定决策。

## 安全与真实性

不得写入密码、token、API key、私有连接串、真实客户数据、旧公司材料或完整敏感请求/响应。日志与测试、Git 或实际服务状态冲突时，以新鲜命令输出为准，并在当日日志记录更正。

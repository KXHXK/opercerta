# OperCerta 公开作品集与面试展示设计

**日期：** 2026-07-18
**状态：** 已确认，待实施计划
**范围：** 仅 OperCerta 及其在个人作品集中的入口；不启动其他项目。

## 1. 目标与非目标

目标是在不虚构线上生产能力的前提下，让招聘人员可即时浏览 OperCerta 的项目价值、工程证据和真实演示材料，并让面试现场可稳定展示真实运行的系统。

本设计不部署公开可写的 Agent 服务，不改变当前 `OperCerta release gate: CLOSED`，不公开 Private GitHub 源码，不引入真实企业数据、虚构指标或旧公司材料。

## 2. 两层展示架构

```text
简历 / HR
  -> 个人作品集首页（静态）
    -> OperCerta 项目入口
      -> OperCerta 公开项目专题（静态）
        -> 真实演示视频、截图、可核验证据

面试现场
  -> localhost /console
    -> Docker Compose
      -> FastAPI -> FastMCP -> PostgreSQL / LangGraph
```

公开项目专题不得请求本机 API、数据库或 MCP 服务；其可用性只依赖静态托管。真实控制台仍通过本机 Docker Compose 运行，作为现场演示和复现路径。

## 3. 个人作品集入口

个人作品集位于 `D:\CODEX\resume\portfolio`，已有单页深色编辑工作室风格。该工作目录当前存在用户未提交改动，实施时必须将其视为基线：仅在项目列表新增一张 OperCerta 卡片，不重写现有内容、不格式化无关文件、不提交用户已有改动。

卡片展示：

- 名称：`OperCerta`；
- 一句事实性描述：面向库存异常处置的可恢复运营 Agent；
- 技术标签：`LANGGRAPH / FASTAPI / MCP / POSTGRESQL`；
- 外链：只在 OperCerta 静态专题已部署并获得真实 HTTPS URL 后写入；不得写入临时、猜测或占位 URL。

## 4. OperCerta 公开专题

在 `web/` 现有 Vite + React 应用内加入显式路径分流：

- `/`：公开项目专题；
- `/console`：既有运营控制台。

公开专题页应包含以下固定区块：

1. 项目问题和最小业务闭环：库存不足、审批绑定、幂等补货工单、审计；
2. 架构与职责边界：React、FastAPI、LangGraph、FastMCP、PostgreSQL、Docker Compose、GitHub Actions；
3. 可靠性证据：非法输入、状态恢复、审批竞态、幂等写入、重启恢复；每项链接到仓库中已有设计或发布证据；
4. 真实演示材料：后续录制的 3--5 分钟视频与从本项目运行环境采集的截图；
5. 诚实边界：Private GitHub、Mock 模型、未完成设备场景、生产 IAM/SSO、自动部署、完整 E2E、公开可写服务均明确标为未完成；发布门禁保持 `CLOSED`；
6. 面试复现说明：说明 `/console` 仅在本机 Docker Compose 已启动时用于真实演示。

不展示未经测量的性能、准确率、可用性或成本数值；不提供会让第三方创建真实工单的公网写入入口。

## 5. 控制台降级行为

`/console` 保留现有真实交互逻辑。未配置本地 API 基地址或请求不可达时，应显示明确、可操作的本地演示提示（例如先启动 Docker Compose），而非无限加载、伪造结果或将故障伪装为线上服务。

公开专题与控制台的路由分离不得改变已验证的审批、审计回放、JWT/RBAC 演示契约。

## 6. 发布顺序

1. 在 OperCerta 中完成公开专题、控制台降级、真实演示材料和测试；
2. 通过本地前端测试、构建和现有 GitHub Actions 门禁；
3. 部署仅含静态展示内容的 OperCerta 专题，并验证 HTTPS URL；
4. 将真实 URL 写入个人作品集 OperCerta 卡片，验证作品集构建；
5. 单独记录展示部署证据，但不得将其描述为 OperCerta 生产发布或打开发布门禁。

## 7. 验收标准

- HR 访问作品集与 OperCerta 专题不依赖用户电脑或本机 Docker 服务；
- 专题中每项技术结论能追溯到已有文档、测试或 CI 证据；
- `/console` 在本地服务不可用时给出明确提示，不伪造业务结果；
- 本地前端测试和构建通过，现有 CI 分层门禁继续通过；
- 作品集只新增 OperCerta 入口，用户在 `D:\CODEX\resume\portfolio` 中已有的未提交改动未被覆盖或提交；
- 发布门禁仍为 `CLOSED`，直至原详细设计规定的完整发布条件另行完成。

# Replenishment Contract Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 为当前 OperCerta 库存补货后端建立冻结的 30 条合成契约回归评测与无敏感信息的逐例报告。

**Architecture:** 评测数据与 Python schema 分离；运行器复用现有 FastAPI/MCP/PostgreSQL 集成夹具，对每条用例建立独立 operation 并清理。报告写入被忽略的 tmp/evals，不影响 Git 数据集的冻结性。

**Tech Stack:** Python 3.12、Pydantic、Pytest、HTTPX、FastAPI、PostgreSQL、FastMCP。

## Global Constraints

- 仅覆盖已实现库存补货后端与合成数据；不加入设备、真实模型、性能、前端、SSE、SSO、公开部署或生产指标。
- 数据集固定为 data/evals/replenishment-v1.json，30 个唯一 ID RPL-001 至 RPL-030；每例必须有 rule_refs。
- 不读取或写入 JWT、密码、数据库 URL、Authorization header、隐藏推理或 MCP 内部异常。
- 数据集期望变化必须升级 suite_version；报告保留全部失败，不以通过率替代逐例结果。
- 先 RED 后 GREEN；发布门禁持续 CLOSED。

---

### Task 1: 评测数据契约

**Files:**
- Create: src/opercerta/evaluation/__init__.py
- Create: src/opercerta/evaluation/contracts.py
- Create: tests/unit/evaluation/test_contracts.py

**Interfaces:**
- Produces EvalCase(id: str, title: str, rule_refs: tuple[str, ...], actor: EvalActor, steps: tuple[EvalStep, ...], expected: EvalExpected).
- Produces load_suite(path: Path) -> EvalSuite and validate_suite(suite: EvalSuite) -> None.

- [ ] **Step 1: 写失败测试**

~~~python
def test_suite_rejects_non_sequential_or_duplicate_case_ids() -> None:
    with pytest.raises(ValidationError):
        EvalSuite.model_validate({"suite_version": "replenishment-v1", "cases": [
            valid_case("RPL-001"), valid_case("RPL-001")
        ]})
~~~

再测试 rule_refs 为空、actor 非 anonymous/operator/approver/auditor/demo-admin、expected 缺失 status_code 均拒绝。

- [ ] **Step 2: 运行 RED**

Run: uv run pytest tests/unit/evaluation/test_contracts.py -q  
Expected: 退出码 1，opercerta.evaluation 模块不存在。

- [ ] **Step 3: 实现最小 schema**

~~~python
class EvalActor(StrEnum):
    ANONYMOUS = "anonymous"
    OPERATOR = "operator"
    APPROVER = "approver"
    AUDITOR = "auditor"
    DEMO_ADMIN = "demo-admin"


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Annotated[str, StringConstraints(pattern=r"^RPL-(?:0[0-9]|[12][0-9]|30)$")]
    title: Annotated[str, StringConstraints(min_length=1, max_length=120)]
    rule_refs: tuple[Annotated[str, StringConstraints(min_length=1)], ...]
    actor: EvalActor
    steps: tuple[dict[str, JsonValue], ...]
    expected: dict[str, JsonValue]
~~~

validate_suite 必须要求 30 个唯一且完整连续 ID、每例至少一条 rule_refs。

- [ ] **Step 4: 验证 GREEN**

Run: uv run pytest tests/unit/evaluation/test_contracts.py -q; uv run ruff check src/opercerta/evaluation tests/unit/evaluation; uv run mypy src/opercerta/evaluation  
Expected: 全部退出码 0。

- [ ] **Step 5: 提交**

~~~bash
git add src/opercerta/evaluation tests/unit/evaluation
git commit -m "feat: define replenishment evaluation contracts"
~~~

### Task 2: 冻结 30 条合成数据集

**Files:**
- Create: data/evals/replenishment-v1.json
- Modify: tests/unit/evaluation/test_contracts.py

**Interfaces:**
- Consumes EvalSuite and load_suite from Task 1.
- Produces suite_version=replenishment-v1 and exactly 30 cases.

- [ ] **Step 1: 写失败数据集测试**

~~~python
def test_frozen_replenishment_suite_has_all_30_rule_referenced_cases() -> None:
    suite = load_suite(Path("data/evals/replenishment-v1.json"))
    assert [case.id for case in suite.cases] == [f"RPL-{number:03d}" for number in range(1, 31)]
    assert all(case.rule_refs for case in suite.cases)
~~~

- [ ] **Step 2: 运行 RED**

Run: uv run pytest tests/unit/evaluation/test_contracts.py::test_frozen_replenishment_suite_has_all_30_rule_referenced_cases -q  
Expected: 退出码 1，数据文件不存在。

- [ ] **Step 3: 写入数据集**

数据集按规格的 5/4/7/6/5/3 分组写入 RPL-001 至 RPL-030。每项 expected 至少声明 status_code；涉及 operation 的项还声明 terminal_status、approval_count、work_order_count 和 audit_event_names。每项 rule_refs 指向 docs/specs/2026-07-14-opercerta-design.md 或稳定错误码。

- [ ] **Step 4: 验证 GREEN**

Run: uv run pytest tests/unit/evaluation/test_contracts.py -q  
Expected: 所有 schema、连续 ID、规则引用和 30 条断言通过。

- [ ] **Step 5: 提交**

~~~bash
git add data/evals/replenishment-v1.json tests/unit/evaluation/test_contracts.py
git commit -m "test: add frozen replenishment evaluation suite"
~~~

### Task 3: 真实边界运行器与报告

**Files:**
- Create: src/opercerta/evaluation/runner.py
- Create: scripts/run_replenishment_evaluation.py
- Create: tests/integration/evaluation/test_runner.py
- Modify: .gitignore

**Interfaces:**
- Consumes EvalSuite.
- Produces async run_suite(suite: EvalSuite, output_dir: Path) -> EvaluationReport.
- Produces JSON report fields suite_version, started_at, finished_at, total, passed, failed, cases.

- [ ] **Step 1: 写失败运行器测试**

~~~python
async def test_runner_records_a_failed_assertion_instead_of_skipping_it(tmp_path: Path) -> None:
    report = await run_suite(single_case_suite(expected_status_code=418), tmp_path)
    assert report.total == 1
    assert report.failed == 1
    assert report.cases[0].failure_summary
    assert (tmp_path / "replenishment-v1-report.json").is_file()
~~~

- [ ] **Step 2: 运行 RED**

Run: uv run pytest tests/integration/evaluation/test_runner.py -q  
Expected: 退出码 1，runner 模块不存在。

- [ ] **Step 3: 实现最小运行器**

运行器为每例使用独立真实 API harness 和角色 token；anonymous 不带 header。每例捕获 AssertionError 并生成 failure_summary，不中止后续用例。报告序列化前删除任何 key 名含 password、token、authorization、database_url 的值。脚本接受 --suite 和 --output-dir，默认输出 tmp/evals。

- [ ] **Step 4: 验证 GREEN**

Run: uv run pytest tests/integration/evaluation/test_runner.py -q; uv run python scripts/run_replenishment_evaluation.py --suite data/evals/replenishment-v1.json --output-dir tmp/evals  
Expected: runner 测试退出码 0；报告存在且包含 30 条逐例结果。

- [ ] **Step 5: 提交**

~~~bash
git add src/opercerta/evaluation scripts/run_replenishment_evaluation.py tests/integration/evaluation .gitignore
git commit -m "feat: run replenishment contract evaluations"
~~~

### Task 4: 门禁、真实报告与文档

**Files:**
- Modify: README.md
- Modify: IMPLEMENTATION_HANDOFF.md
- Modify: DOCUMENT_INDEX.md
- Modify: docs/development-log/current-state.md
- Modify: docs/development-log/daily/2026-07-18.md
- Modify: docs/development-log/interview-casebook.md
- Create: docs/release-evidence/replenishment-contract-evaluation.md

- [ ] **Step 1: 运行真实套件与全量门禁**

Run: uv run python scripts/run_replenishment_evaluation.py --suite data/evals/replenishment-v1.json --output-dir tmp/evals; uv run pytest -q; uv run ruff check .; uv run ruff format --check .; uv run mypy src  
Expected: 评测报告 failed=0；其他命令退出码 0。

- [ ] **Step 2: 写入实际证据**

记录真实 suite_version、用例数、通过/失败数、运行命令、环境范围、报告路径、失败时如何保留证据和未实施限制。禁止写准确率、生产效果或虚构指标。

- [ ] **Step 3: 验证并提交**

Run: git diff --check; git status --short  
Expected: 无敏感文件、无 tmp/evals 报告进入 Git。

~~~bash
git add README.md IMPLEMENTATION_HANDOFF.md DOCUMENT_INDEX.md docs
git commit -m "docs: record replenishment contract evaluation"
~~~

## 自审结果

- Task 1 覆盖 schema、角色、固定 ID 与规则引用；Task 2 覆盖冻结的 30 条合成数据；Task 3 覆盖真实边界、完整失败报告与脱敏；Task 4 覆盖门禁与诚实证据。
- 类型名只在定义后的任务被使用；数据集、报告和 Git 忽略规则的边界明确。


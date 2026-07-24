import { useState } from "react";

import type { DemoRole } from "../session";
import { operationScenarios, type OperationAction, type ScenarioDefinition } from "../scenarios";

type OperationControlsProps = {
  role: DemoRole;
  isAuthenticated: boolean;
  onRoleChange: (role: DemoRole) => void;
  onCreate: (scenario: ScenarioDefinition, action: OperationAction) => void;
  onLoad: (operationId: string) => void;
};

export function OperationControls({
  role,
  isAuthenticated,
  onRoleChange,
  onCreate,
  onLoad
}: OperationControlsProps) {
  const [objectType, setObjectType] = useState<ScenarioDefinition["objectType"]>("inventory");
  const [operationId, setOperationId] = useState("");
  const scenario = operationScenarios.find((item) => item.objectType === objectType) ?? operationScenarios[0];

  return (
    <section aria-label="操作控制区">
      <label className="field-label" htmlFor="demo-role">演示角色</label>
      <select id="demo-role" value={role} onChange={(event) => onRoleChange(event.target.value as DemoRole)}>
        <option value="operator">operator｜创建处置</option>
        <option value="approver">approver｜提交审批</option>
        <option value="auditor">auditor｜审计读取</option>
      </select>

      <label className="field-label" htmlFor="business-scenario">业务场景</label>
      <select
        id="business-scenario"
        value={objectType}
        onChange={(event) => setObjectType(event.target.value as ScenarioDefinition["objectType"])}
      >
        {operationScenarios.map((item) => (
          <option key={item.objectType} value={item.objectType}>{item.label}</option>
        ))}
      </select>
      <div className="scenario-brief">
        <strong>{scenario.objectId}</strong>
        <span>{scenario.explanation}</span>
      </div>
      <div className="scenario-actions">
        <button
          type="button"
          disabled={!isAuthenticated || role !== "operator"}
          onClick={() => onCreate(scenario, "query")}
        >
          查询状态
        </button>
        <button
          type="button"
          disabled={!isAuthenticated || role !== "operator"}
          onClick={() => onCreate(scenario, "create_work_order")}
        >
          创建处置
        </button>
      </div>

      <label className="field-label" htmlFor="operation-id">处置编号</label>
      <div className="inline-fields">
        <input
          id="operation-id"
          value={operationId}
          onChange={(event) => setOperationId(event.target.value)}
          placeholder="粘贴 operation_id"
        />
        <button
          type="button"
          disabled={!isAuthenticated || operationId.trim().length === 0}
          onClick={() => onLoad(operationId.trim())}
        >
          读取处置
        </button>
      </div>
      <p className="panel-note">切换角色后会重新获取仅存于内存中的演示 JWT。</p>
    </section>
  );
}

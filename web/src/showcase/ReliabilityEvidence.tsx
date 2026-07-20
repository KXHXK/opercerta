const RELIABILITY = [
  ["审批绑定", "证据 ID、规则版本、事实哈希、计划哈希和类型化参数共同绑定批准内容。"],
  ["原子竞态", "PostgreSQL 行锁让并发审批只有一个胜者，失败者得到稳定冲突。"],
  ["幂等写入", "operation 派生幂等键与唯一约束，使 LangGraph 重放不产生第二张工单。"],
  ["重启恢复", "业务表定位非终态 operation，checkpoint 恢复执行位置，事实不一致时安全失败。"],
] as const;

export function ReliabilityEvidence() {
  return (
    <div className="reliability-grid">
      {RELIABILITY.map(([title, text]) => (
        <article key={title}>
          <h3>{title}</h3>
          <p>{text}</p>
        </article>
      ))}
    </div>
  );
}

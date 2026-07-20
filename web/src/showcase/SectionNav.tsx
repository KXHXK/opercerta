const ITEMS = [
  ["business", "业务"],
  ["flow", "流程"],
  ["architecture", "架构"],
  ["evidence", "证据"],
] as const;

export function SectionNav() {
  function moveTo(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <nav className="section-nav" aria-label="项目专题目录">
      <a className="showcase-logo" href="/">
        OPERCERTA
      </a>
      <div>
        {ITEMS.map(([id, label]) => (
          <button key={id} type="button" onClick={() => moveTo(id)}>
            {label}
          </button>
        ))}
      </div>
    </nav>
  );
}

import { TECHNOLOGIES } from "./engineering-content";

export function TechnologyMap() {
  return (
    <section className="engineering-section" aria-labelledby="technology-map-title">
      <p className="section-kicker">TECHNOLOGY EFFECT</p>
      <h2 id="technology-map-title">技术不是清单，而是可验证职责</h2>
      <div className="technology-map">
        {TECHNOLOGIES.map((technology) => (
          <article key={technology.name}>
            <h3>{technology.name}</h3>
            <p>{technology.responsibility}</p>
            <strong>{technology.verifiedEffect}</strong>
          </article>
        ))}
      </div>
    </section>
  );
}

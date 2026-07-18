import { SacredGeometry } from "./SacredGeometry";

type GodCoreProps = {
  activity: number;
};

export function GodCore({ activity }: GodCoreProps) {
  return (
    <section className="god-core exact-god" style={{ "--god-activity": activity } as React.CSSProperties}>
      <div className="god-title">
        <strong>D E U S</strong>
        <span>PRESENTE</span>
      </div>
      <div className="god-sphere">
        <span className="god-rays" />
        <SacredGeometry className="god-geometry" />
        <span className="god-white-core" />
      </div>
      <div className="god-caption">
        <span>Consciência Suprema</span>
        <em>Estou ouvindo.</em>
      </div>
    </section>
  );
}

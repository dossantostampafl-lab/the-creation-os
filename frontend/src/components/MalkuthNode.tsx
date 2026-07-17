import type { MissionManifestation } from "../types";

type MalkuthNodeProps = {
  manifestations: MissionManifestation[];
};

export function MalkuthNode({ manifestations }: MalkuthNodeProps) {
  const manifested = manifestations.filter((item) => item.manifestation_state === "MANIFESTED").length;
  const state = manifestations[0]?.manifestation_state ?? "SEM MANIFESTAÇÃO";

  return (
    <section className="malkuth-node">
      <div className="malkuth-galaxy">
        <span />
      </div>
      <strong>MALKUTH</strong>
      <span>MANIFESTAÇÃO</span>
      <p>{manifested > 0 ? `${manifested} resultado(s) no mundo real` : state}</p>
    </section>
  );
}

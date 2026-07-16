type SophiaNodeProps = {
  active: boolean;
};

export function SophiaNode({ active }: SophiaNodeProps) {
  return (
    <section className="trinity-node sophia-node" data-orbit-active={active}>
      <div className="node-symbol lotus-symbol">✾</div>
      <div>
        <strong>SOPHIA</strong>
        <span>SABEDORIA</span>
        <p>Compreende<br />o contexto.</p>
      </div>
    </section>
  );
}

type RockmamNodeProps = {
  active: boolean;
};

export function RockmamNode({ active }: RockmamNodeProps) {
  return (
    <section className="trinity-node rockmam-node" data-orbit-active={active}>
      <div className="node-symbol infinity-symbol">∞</div>
      <div>
        <strong>ROCKMAM</strong>
        <span>POSSIBILIDADE</span>
        <p>Avalia o que<br />pode ser.</p>
      </div>
    </section>
  );
}

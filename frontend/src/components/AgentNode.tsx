type AgentNodeProps = {
  title: string;
  subtitle: string;
  active: boolean;
};

export function AgentNode({ title, subtitle, active }: AgentNodeProps) {
  return (
    <article className="agent-node" data-agent-executing={active}>
      <div className="agent-orb">
        <span />
      </div>
      <strong>{title}</strong>
      <em>{subtitle}</em>
    </article>
  );
}

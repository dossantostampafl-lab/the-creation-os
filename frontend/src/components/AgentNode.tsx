type AgentNodeProps = {
  title: string;
  subtitle: string;
};

export function AgentNode({ title, subtitle }: AgentNodeProps) {
  return (
    <article className="agent-node">
      <div className="agent-orb">
        <span />
      </div>
      <strong>{title}</strong>
      <em>{subtitle}</em>
    </article>
  );
}

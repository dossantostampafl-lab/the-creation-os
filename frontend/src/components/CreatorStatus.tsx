import { UserRound } from "lucide-react";

type CreatorStatusProps = {
  authenticated: boolean;
};

export function CreatorStatus({ authenticated }: CreatorStatusProps) {
  return (
    <section className="creator-status">
      <div className="creator-clock">
        <strong>09:41:22</strong>
        <span>13 JUL 2026</span>
      </div>
      <div className="creator-access">
        <strong>CRIADOR</strong>
        <span>{authenticated ? "Acesso total" : "Acesso bloqueado"}</span>
      </div>
      <div className="creator-icon">
        <UserRound size={22} />
      </div>
    </section>
  );
}

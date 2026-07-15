import { useEffect, useState } from "react";
import { UserRound } from "lucide-react";

type CreatorStatusProps = {
  authenticated: boolean;
};

export function CreatorStatus({ authenticated: _authenticated }: CreatorStatusProps) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const interval = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  const time = new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(now);
  const day = new Intl.DateTimeFormat(undefined, { day: "2-digit" }).format(now);
  const month = new Intl.DateTimeFormat(undefined, { month: "short" }).format(now).replace(".", "").toUpperCase();
  const year = new Intl.DateTimeFormat(undefined, { year: "numeric" }).format(now);
  const date = `${day} ${month} ${year}`;

  return (
    <section className="creator-status">
      <div className="creator-clock">
        <strong>{time}</strong>
        <span>{date}</span>
      </div>
      <div className="creator-access">
        <strong>CRIADOR</strong>
        <span>Acesso total</span>
      </div>
      <div className="creator-icon">
        <UserRound size={22} />
      </div>
    </section>
  );
}

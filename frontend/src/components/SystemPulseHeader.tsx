import type { ReactNode } from "react";
import type { Pulse } from "../types";

type SystemPulseHeaderProps = {
  pulse: Pulse | null;
  authenticated: boolean;
  unreadNotificationCount: number;
  onOpenSearch: () => void;
  onOpenNotifications: () => void;
};

/**
 * Every number here comes from real /api/v1/pulse data — nothing is
 * decorative or randomized. The score is a simple, transparent weighted
 * readout of the same signals Pulse already reports (db/redis/streams
 * health, chronicle chain integrity, failed tasks, error count), not a
 * separate metric invented for this header.
 */
export function computePulseScore(pulse: Pulse | null): number {
  if (!pulse) return 0;
  let score = 100;
  if (pulse.database?.status === "error") score -= 25;
  if (pulse.redis?.status === "error") score -= 20;
  if (pulse.redis_streams?.status === "error") score -= 15;
  if (!pulse.chronicles_chain?.valid) score -= 25;
  score -= Math.min(10, pulse.failed_tasks ?? 0);
  score -= Math.min(10, pulse.error_count ?? 0);
  return Math.max(0, Math.min(100, Math.round(score)));
}

function pulseStatusLabel(pulse: Pulse | null): string {
  if (!pulse) return "VERIFICANDO";
  if (pulse.status === "live") return "ESTÁVEL";
  if (pulse.status === "degraded") return "DEGRADADO";
  return "CRÍTICO";
}

function LogoMark() {
  return (
    <svg viewBox="0 0 40 40" width="34" height="34" aria-hidden="true" className="brand-mark">
      <circle cx="20" cy="20" r="18" fill="none" stroke="currentColor" strokeWidth="0.6" opacity="0.35" />
      <circle cx="20" cy="20" r="12" fill="none" stroke="currentColor" strokeWidth="0.6" opacity="0.55" />
      <circle cx="20" cy="12" r="7" fill="none" stroke="currentColor" strokeWidth="0.6" />
      <circle cx="13.9" cy="16" r="7" fill="none" stroke="currentColor" strokeWidth="0.6" />
      <circle cx="26.1" cy="16" r="7" fill="none" stroke="currentColor" strokeWidth="0.6" />
      <circle cx="13.9" cy="24" r="7" fill="none" stroke="currentColor" strokeWidth="0.6" />
      <circle cx="26.1" cy="24" r="7" fill="none" stroke="currentColor" strokeWidth="0.6" />
      <circle cx="20" cy="28" r="7" fill="none" stroke="currentColor" strokeWidth="0.6" />
      <circle cx="20" cy="20" r="2.2" fill="currentColor" />
    </svg>
  );
}

function PulseWave({ healthy }: { healthy: boolean }) {
  return (
    <svg viewBox="0 0 220 32" width="220" height="32" className={`pulse-wave ${healthy ? "is-healthy" : "is-degraded"}`} aria-hidden="true">
      <polyline
        className="pulse-wave-line"
        fill="none"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        points="0,16 26,16 34,16 40,4 46,28 52,16 60,16 88,16 96,16 102,4 108,28 114,16 122,16 150,16 158,16 164,4 170,28 176,16 184,16 220,16"
      />
    </svg>
  );
}

function HeaderIconButton({
  label,
  onClick,
  badge,
  children,
}: {
  label: string;
  onClick: () => void;
  badge?: number;
  children: ReactNode;
}) {
  return (
    <button type="button" className="header-icon-button" aria-label={label} title={label} onClick={onClick}>
      {children}
      {badge && badge > 0 ? <span className="header-icon-badge">{badge > 9 ? "9+" : badge}</span> : null}
    </button>
  );
}

export function SystemPulseHeader({ pulse, authenticated, unreadNotificationCount, onOpenSearch, onOpenNotifications }: SystemPulseHeaderProps) {
  const score = computePulseScore(pulse);
  const healthy = pulse?.status === "live";

  return (
    <header className="system-pulse-header" aria-label="Cabecalho do sistema">
      <div className="brand-block">
        <LogoMark />
        <div className="brand-text">
          <strong>THE CREATION OS</strong>
          <span>LIVING CORE</span>
        </div>
      </div>

      <div className="pulse-block" role="status" aria-live="polite">
        <span className="pulse-label">PULSO DO SISTEMA</span>
        <PulseWave healthy={healthy} />
        <div className={`pulse-score tone-${healthy ? "healthy" : pulse ? "degraded" : "unknown"}`}>
          <svg viewBox="0 0 36 36" width="46" height="46" aria-hidden="true">
            <circle cx="18" cy="18" r="15.5" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="2" />
            <circle
              cx="18"
              cy="18"
              r="15.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeDasharray={`${(score / 100) * 97.4} 97.4`}
              transform="rotate(-90 18 18)"
            />
          </svg>
          <div className="pulse-score-text">
            <strong>{score}%</strong>
            <span>{pulseStatusLabel(pulse)}</span>
          </div>
        </div>
      </div>

      <div className="header-right">
        {authenticated ? (
          <div className="header-actions">
            <HeaderIconButton label="Buscar" onClick={onOpenSearch}>
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                <circle cx="11" cy="11" r="7" />
                <path d="M21 21l-4.3-4.3" strokeLinecap="round" />
              </svg>
            </HeaderIconButton>
            <HeaderIconButton label="Notificacoes" onClick={onOpenNotifications} badge={unreadNotificationCount}>
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                <path d="M6 10a6 6 0 1 1 12 0c0 4 1.5 5.5 1.5 5.5H4.5S6 14 6 10Z" strokeLinejoin="round" />
                <path d="M10 18.5a2 2 0 0 0 4 0" strokeLinecap="round" />
              </svg>
            </HeaderIconButton>
          </div>
        ) : null}

        <div className="creator-badge" aria-hidden={!authenticated}>
          {authenticated ? (
            <>
              <div className="creator-badge-text">
                <strong>CRIADOR</strong>
                <span>ACESSO TOTAL</span>
              </div>
              <span className="creator-badge-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.4">
                  <circle cx="12" cy="8" r="3.6" />
                  <path d="M4.5 20c1.4-4 4-6 7.5-6s6.1 2 7.5 6" strokeLinecap="round" />
                </svg>
              </span>
            </>
          ) : null}
        </div>
      </div>
    </header>
  );
}

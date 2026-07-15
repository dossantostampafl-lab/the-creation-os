export function SacredGeometry({ className = "" }: { className?: string }) {
  const circles = Array.from({ length: 6 }, (_, index) => index);
  return (
    <svg className={`sacred-geometry ${className}`} viewBox="0 0 100 100" aria-hidden="true">
      <circle cx="50" cy="50" r="18" />
      <circle cx="50" cy="50" r="29" />
      <circle cx="50" cy="50" r="40" />
      {circles.map((item) => {
        const angle = (item / circles.length) * Math.PI * 2;
        return <circle key={item} cx={50 + Math.cos(angle) * 18} cy={50 + Math.sin(angle) * 18} r="18" />;
      })}
      <path d="M50 10 L84 70 L16 70 Z" />
      <path d="M50 90 L84 30 L16 30 Z" />
    </svg>
  );
}

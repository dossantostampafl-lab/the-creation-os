type ConnectionLayerProps = {
  flowActive: boolean;
  runningMissions: number;
  pendingInceptions: number;
  manifested: number;
};

export function ConnectionLayer({ flowActive, runningMissions, pendingInceptions, manifested }: ConnectionLayerProps) {
  return (
    <svg
      className="connection-layer"
      viewBox="0 0 1536 1024"
      preserveAspectRatio="none"
      aria-hidden="true"
      data-flow-active={flowActive}
      data-running-missions={runningMissions}
      data-pending-inceptions={pendingInceptions}
      data-manifested={manifested}
    >
      <path className="orbit-line gold" d="M300 378 C520 210 1020 190 1300 380" />
      <path className="orbit-line blue" d="M68 455 C410 316 785 327 1255 456" />
      <path className="orbit-line amber" d="M180 690 C530 514 998 514 1430 695" />
      <path className="energy-line trinity-flow sophia-flow" d="M767 350 C690 340 650 318 615 292" />
      <path className="energy-line trinity-flow rockmam-flow" d="M767 350 C845 344 900 323 950 300" />
      <path className="energy-line inception-flow" d="M767 350 C630 360 512 392 300 430" />
      <path className="energy-line bright core-flow" d="M767 350 C767 425 767 495 768 560" />
      <path className="energy-line bright agent-flow" d="M610 645 C690 632 850 632 930 645" />
      <path className="energy-line bright malkuth-flow" d="M768 560 C768 656 768 758 768 875" />
      <path className="energy-line bright manifestation-flow" d="M767 350 C972 362 1110 410 1310 392" />
    </svg>
  );
}

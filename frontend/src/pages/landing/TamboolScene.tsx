/**
 * Lamp-lit editorial illustration of a Tambool being prepared: a brass thali on a red chowki cloth
 * with betel leaves, supari, marigolds, rose petals, kumkum and haldi, and a diya. Drawn in SVG so
 * it stays sharp at any width, costs no download, and can later be swapped for real photography or
 * video without changing the hero layout. Decorative motion is opt-in via `motion-safe:`.
 */

/** Betel leaf: heart-shaped base at the stem, drawn tip-down at the origin. */
const LEAF = "M0 -62 C30 -64 58 -40 52 -6 C47 24 22 46 0 78 C-22 46 -47 24 -52 -6 C-58 -40 -30 -64 0 -62 Z";

function Leaf({ x, y, r = 0, s = 1, shade = "a" }: { x: number; y: number; r?: number; s?: number; shade?: "a" | "b" }) {
  return (
    <g transform={`translate(${x} ${y}) rotate(${r}) scale(${s})`}>
      <path d={LEAF} fill={`url(#leaf-${shade})`} stroke="#1f4d2b" strokeWidth="1.2" />
      <path d="M0 -58 C2 -10 1 30 0 74" fill="none" stroke="#c8e3a5" strokeWidth="2" opacity="0.7" />
      {[-34, -12, 10, 32].map((v) => (
        <g key={v} fill="none" stroke="#c8e3a5" strokeWidth="1.1" opacity="0.45">
          <path d={`M0 ${v} Q20 ${v - 6} 36 ${v - 20}`} />
          <path d={`M0 ${v} Q-20 ${v - 6} -36 ${v - 20}`} />
        </g>
      ))}
    </g>
  );
}

function Marigold({ x, y, s = 1 }: { x: number; y: number; s?: number }) {
  return (
    <g transform={`translate(${x} ${y}) scale(${s})`}>
      <circle r="26" fill="#e8850c" />
      {Array.from({ length: 14 }, (_, i) => (
        <ellipse key={`o${i}`} rx="8" ry="14" cy="-17" fill="#f59e0b" stroke="#c2410c" strokeWidth="0.6" transform={`rotate(${(360 / 14) * i})`} />
      ))}
      {Array.from({ length: 10 }, (_, i) => (
        <ellipse key={`i${i}`} rx="6" ry="9" cy="-9" fill="#fbbf24" stroke="#d97706" strokeWidth="0.5" transform={`rotate(${(360 / 10) * i + 18})`} />
      ))}
      <circle r="5" fill="#b45309" />
    </g>
  );
}

function Supari({ x, y, r = 0 }: { x: number; y: number; r?: number }) {
  return (
    <g transform={`translate(${x} ${y}) rotate(${r})`}>
      <ellipse rx="13" ry="10" fill="url(#supari)" />
      <path d="M-9 -2 Q0 -7 9 -1 M-8 4 Q0 0 8 5" stroke="#f3d9b1" strokeWidth="1.2" fill="none" opacity="0.55" />
    </g>
  );
}

function Petal({ x, y, r = 0, c = "#b91c1c" }: { x: number; y: number; r?: number; c?: string }) {
  return <path d="M0 0 C8 -10 20 -6 18 6 C14 14 2 12 0 0 Z" transform={`translate(${x} ${y}) rotate(${r})`} fill={c} opacity="0.9" />;
}

const BOKEH: [number, number, number][] = [
  [90, 120, 26], [240, 70, 14], [380, 150, 20], [560, 60, 12], [720, 130, 30], [900, 50, 16], [1060, 110, 22],
  [1230, 70, 12], [1380, 140, 28], [1520, 60, 18], [160, 300, 10], [1460, 320, 12], [640, 260, 9], [1000, 250, 11],
];

export function TamboolScene({ className = "", label }: { className?: string; label: string }) {
  return (
    <svg viewBox="0 0 1600 900" preserveAspectRatio="xMidYMid slice" className={className} role="img" aria-label={label}>
      <defs>
        <radialGradient id="dusk" cx="68%" cy="62%" r="85%">
          <stop offset="0" stopColor="#7c2d12" />
          <stop offset="0.45" stopColor="#4a1a0c" />
          <stop offset="1" stopColor="#1c0b05" />
        </radialGradient>
        <radialGradient id="lamp" cx="50%" cy="50%" r="50%">
          <stop offset="0" stopColor="#fde68a" stopOpacity="0.55" />
          <stop offset="0.4" stopColor="#f59e0b" stopOpacity="0.18" />
          <stop offset="1" stopColor="#f59e0b" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="cloth" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#9f1d1d" />
          <stop offset="1" stopColor="#5f0f0f" />
        </linearGradient>
        <radialGradient id="brass" cx="45%" cy="35%" r="70%">
          <stop offset="0" stopColor="#fff1b8" />
          <stop offset="0.35" stopColor="#e7b54a" />
          <stop offset="0.75" stopColor="#b7791f" />
          <stop offset="1" stopColor="#7a4a0d" />
        </radialGradient>
        <radialGradient id="brass-inner" cx="50%" cy="40%" r="65%">
          <stop offset="0" stopColor="#f6d27a" />
          <stop offset="1" stopColor="#a86b17" />
        </radialGradient>
        <linearGradient id="leaf-a" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#5fa04a" />
          <stop offset="1" stopColor="#23592f" />
        </linearGradient>
        <linearGradient id="leaf-b" x1="1" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#7cb85a" />
          <stop offset="1" stopColor="#2f6b36" />
        </linearGradient>
        <radialGradient id="supari" cx="40%" cy="35%" r="70%">
          <stop offset="0" stopColor="#c8895a" />
          <stop offset="1" stopColor="#6b3a1d" />
        </radialGradient>
        <radialGradient id="flame" cx="50%" cy="70%" r="60%">
          <stop offset="0" stopColor="#fffbeb" />
          <stop offset="0.4" stopColor="#fcd34d" />
          <stop offset="1" stopColor="#f97316" />
        </radialGradient>
        <filter id="soft" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="6" />
        </filter>
        <filter id="shadow" x="-20%" y="-20%" width="140%" height="160%">
          <feDropShadow dx="0" dy="14" stdDeviation="14" floodColor="#1c0b05" floodOpacity="0.55" />
        </filter>
      </defs>

      {/* dusk room with festival lights */}
      <rect width="1600" height="900" fill="url(#dusk)" />
      <g filter="url(#soft)">
        {BOKEH.map(([x, y, r], i) => (
          <circle key={i} cx={x} cy={y} r={r} fill={i % 3 ? "#fbbf24" : "#fb923c"} opacity={0.22 + (i % 4) * 0.06} />
        ))}
      </g>

      {/* marigold garland hanging across the top */}
      <path d="M-20 40 Q400 170 800 70 T1620 60" fill="none" stroke="#5a3a0a" strokeWidth="2" opacity="0.6" />
      {Array.from({ length: 22 }, (_, i) => {
        const t = i / 21;
        const x = -10 + t * 1630;
        const y = 40 + Math.sin(t * Math.PI * 2) * 55 * (t < 0.5 ? 1 : 0.4) + 30 * Math.sin(t * Math.PI);
        return <Marigold key={i} x={x} y={y} s={0.55 + (i % 3) * 0.06} />;
      })}

      {/* red chowki cloth with a gold zari border */}
      <path d="M120 900 L420 520 L1720 520 L1720 900 Z" fill="url(#cloth)" />
      <path d="M420 520 L1720 520" stroke="#e7b54a" strokeWidth="6" />
      <path d="M405 540 L1720 540" stroke="#e7b54a" strokeWidth="1.5" strokeDasharray="10 8" opacity="0.8" />

      {/* rangoli dots on the cloth */}
      <g fill="#fde68a" opacity="0.45">
        {Array.from({ length: 18 }, (_, i) => (
          <circle key={i} cx={520 + i * 58} cy={860 - (i % 2) * 14} r="3" />
        ))}
      </g>

      {/* lamp glow */}
      <ellipse cx="1330" cy="560" rx="360" ry="300" fill="url(#lamp)" />

      {/* brass thali */}
      <g filter="url(#shadow)">
        <ellipse cx="1050" cy="690" rx="360" ry="130" fill="url(#brass)" />
      </g>
      <ellipse cx="1050" cy="684" rx="330" ry="114" fill="none" stroke="#fff1b8" strokeWidth="2" opacity="0.6" />
      <ellipse cx="1050" cy="690" rx="290" ry="98" fill="url(#brass-inner)" />
      <g fill="none" stroke="#7a4a0d" strokeWidth="1.4" opacity="0.5">
        <ellipse cx="1050" cy="690" rx="310" ry="106" strokeDasharray="4 7" />
        <ellipse cx="1050" cy="690" rx="120" ry="40" />
      </g>

      {/* betel leaves fanned on the thali */}
      <Leaf x={930} y={660} r={-58} s={1.05} />
      <Leaf x={990} y={640} r={-24} s={1.1} shade="b" />
      <Leaf x={1060} y={636} r={8} s={1.12} />
      <Leaf x={1128} y={648} r={38} s={1.05} shade="b" />
      <Leaf x={1180} y={676} r={70} s={0.95} />

      {/* folded paan bida with a clove */}
      <g transform="translate(1000 736) rotate(-10)">
        <path d="M-34 0 L0 -26 L34 0 L0 22 Z" fill="url(#leaf-b)" stroke="#1f4d2b" strokeWidth="1.2" />
        <path d="M-34 0 L34 0" stroke="#c8e3a5" strokeWidth="1" opacity="0.6" />
        <path d="M0 -30 V8" stroke="#3b2210" strokeWidth="3" strokeLinecap="round" />
        <circle cx="0" cy="-31" r="4" fill="#3b2210" />
      </g>

      {/* supari heap */}
      {(
        [
          [1116, 740, 10], [1140, 728, -20], [1164, 744, 30], [1132, 756, 0], [1156, 760, -35], [1182, 732, 15], [1108, 762, 40],
        ] as [number, number, number][]
      ).map(([x, y, r], i) => (
        <Supari key={i} x={x} y={y} r={r} />
      ))}

      {/* kumkum and haldi katoris */}
      <ellipse cx="880" cy="742" rx="42" ry="16" fill="#b7791f" />
      <ellipse cx="880" cy="738" rx="34" ry="11" fill="#b91c1c" />
      <ellipse cx="1240" cy="728" rx="38" ry="14" fill="#b7791f" />
      <ellipse cx="1240" cy="724" rx="30" ry="10" fill="#eab308" />

      {/* flowers on the thali */}
      <Marigold x={930} y={704} s={0.9} />
      <Marigold x={1270} y={680} s={0.8} />
      <Marigold x={1060} y={760} s={0.7} />
      {(
        [
          [960, 752, 20], [1020, 772, -40], [1210, 758, 60], [1286, 712, -10], [896, 700, 80], [1098, 704, 130],
        ] as [number, number, number][]
      ).map(([x, y, r], i) => (
        <Petal key={i} x={x} y={y} r={r} c={i % 2 ? "#be123c" : "#b91c1c"} />
      ))}

      {/* diya with a flickering flame */}
      <g transform="translate(1390 640)">
        <circle r="120" fill="url(#lamp)" />
        <path d="M-52 10 Q0 58 52 10 Q30 -2 0 -2 Q-30 -2 -52 10 Z" fill="#9a3412" stroke="#7c2d12" strokeWidth="2" />
        <path d="M-40 8 Q0 18 40 8" fill="none" stroke="#fbbf24" strokeWidth="2" opacity="0.7" />
        <g className="motion-safe:animate-flicker" style={{ transformBox: "fill-box", transformOrigin: "50% 100%" }}>
          <path d="M0 4 C-12 -14 -8 -34 0 -54 C8 -34 12 -14 0 4 Z" fill="url(#flame)" />
          <circle cy="-22" r="30" fill="#fde68a" opacity="0.25" filter="url(#soft)" />
        </g>
      </g>

      {/* loose petals and a leaf on the cloth */}
      <Leaf x={640} y={820} r={-100} s={0.7} shade="b" />
      <Marigold x={560} y={640} s={0.6} />
      <Marigold x={1500} y={820} s={0.75} />
      {(
        [
          [700, 700, 10], [760, 760, -30], [610, 740, 70], [1460, 740, 40], [1540, 700, -60], [820, 840, 100], [1330, 830, 15],
        ] as [number, number, number][]
      ).map(([x, y, r], i) => (
        <Petal key={i} x={x} y={y} r={r} c={i % 3 ? "#ea580c" : "#be123c"} />
      ))}
    </svg>
  );
}

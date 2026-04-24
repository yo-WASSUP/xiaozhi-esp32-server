import { C } from '../theme';

// 远山（底部一条横向墨色）
export function InkMountains() {
  return (
    <svg viewBox="0 0 700 380" preserveAspectRatio="xMidYMax slice"
      style={{ position: 'absolute', bottom: 0, left: 0, right: 0, width: '100%', height: '34%', pointerEvents: 'none', animation: 'mistFloat 8s ease-in-out infinite' }}>
      <path d="M0,340 Q90,270 180,300 Q270,240 360,275 Q450,245 540,270 Q620,255 700,270 L700,380 L0,380 Z" fill="#7a9299" opacity=".05" />
      <path d="M0,350 Q80,290 170,315 Q260,270 350,300 Q440,272 530,295 Q615,278 700,295 L700,380 L0,380 Z" fill="#7a9299" opacity=".07" />
      <path d="M0,358 Q60,310 120,330 Q190,285 260,318 Q330,292 400,320 Q470,298 545,322 Q620,305 700,318 L700,380 L0,380 Z" fill="#7a9299" opacity=".10" />
      <path d="M0,368 Q50,345 110,358 Q175,338 250,356 Q320,340 400,360 Q480,344 560,360 Q635,348 700,358 L700,380 L0,380 Z" fill="#7a9299" opacity=".13" />
      <path d="M0,376 Q80,365 170,374 Q260,363 360,375 Q460,364 560,375 Q640,366 700,374 L700,380 Z" fill="#7a9299" opacity=".09" />
    </svg>
  );
}

// 近景芦苇（右下角小丛）
export function InkReeds() {
  return (
    <svg viewBox="0 0 160 480" preserveAspectRatio="xMaxYMax meet"
      style={{ position: 'absolute', right: 32, bottom: 0, width: 120, height: 320, pointerEvents: 'none', opacity: .85 }}>
      <line x1="115" y1="480" x2="108" y2="40" stroke={C.inkMid} strokeWidth="1.8" opacity=".13" strokeLinecap="round" />
      <line x1="98" y1="480" x2="104" y2="90" stroke={C.inkMid} strokeWidth="1.2" opacity=".09" strokeLinecap="round" />
      <line x1="128" y1="480" x2="120" y2="130" stroke={C.inkMid} strokeWidth=".9" opacity=".07" strokeLinecap="round" />
      <line x1="85" y1="480" x2="92" y2="160" stroke={C.inkMid} strokeWidth=".7" opacity=".06" strokeLinecap="round" />
      <ellipse cx="108" cy="42" rx="9" ry="22" fill={C.inkMid} opacity=".11" transform="rotate(-4,108,42)" />
      <ellipse cx="104" cy="92" rx="7" ry="17" fill={C.inkMid} opacity=".08" transform="rotate(3,104,92)" />
      <ellipse cx="120" cy="132" rx="5.5" ry="14" fill={C.inkMid} opacity=".06" transform="rotate(-2,120,132)" />
    </svg>
  );
}

import { useEffect, useRef } from 'react';

/** 说话时的波形圆环 canvas；只在 state === 'speaking' 时运行 RAF 循环 */
export function useWaveCanvas(state) {
  const ref = useRef(null);
  const raf = useRef(null);
  const t = useRef(0);

  useEffect(() => {
    if (state !== 'speaking') { cancelAnimationFrame(raf.current); return; }
    const canvas = ref.current; if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height, cx = W / 2, cy = H / 2, R = 76;

    function draw() {
      ctx.clearRect(0, 0, W, H);
      t.current += 0.045;
      ctx.beginPath();
      for (let i = 0; i <= 140; i++) {
        const a = (i / 140) * Math.PI * 2;
        const n = Math.sin(a * 3 + t.current * 2) * 13
          + Math.sin(a * 5 - t.current * 1.6) * 9
          + Math.sin(a * 8 + t.current * 2.9) * 5
          + Math.sin(a * 13 - t.current * 1.2) * 3;
        const r = R + n, x = cx + Math.cos(a) * r, y = cy + Math.sin(a) * r;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
      }
      ctx.closePath();
      const g = ctx.createRadialGradient(cx, cy, R - 18, cx, cy, R + 28);
      g.addColorStop(0, 'rgba(212,146,74,0.45)');
      g.addColorStop(1, 'rgba(212,146,74,0.05)');
      ctx.fillStyle = g; ctx.fill();
      ctx.strokeStyle = 'rgba(200,125,55,0.65)';
      ctx.lineWidth = 2.2; ctx.stroke();
      raf.current = requestAnimationFrame(draw);
    }
    draw();
    return () => cancelAnimationFrame(raf.current);
  }, [state]);

  return ref;
}

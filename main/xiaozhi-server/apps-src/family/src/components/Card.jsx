import { C } from '../theme';

export default function Card({ children, style = {} }) {
  return (
    <div style={{ background: C.card, backdropFilter: 'blur(12px)', borderRadius: 20, border: `1px solid rgba(143,163,176,0.18)`, boxShadow: '0 2px 16px rgba(0,0,0,0.06)', ...style }}>
      {children}
    </div>
  );
}

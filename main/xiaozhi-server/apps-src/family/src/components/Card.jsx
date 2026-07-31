import { C } from '../theme';

export default function Card({ children, style = {} }) {
  return (
    <div style={{ background: C.card, borderRadius: 16, border: `1px solid ${C.outline}`, boxShadow: '0 1px 2px rgba(23,33,28,.05), 0 8px 28px rgba(47,107,85,.05)', ...style }}>
      {children}
    </div>
  );
}

import { C } from '../theme';

export default function SLabel({ children }) {
  return (
    <div style={{ fontSize: 13, color: C.inkMid, fontFamily: 'Noto Sans SC', fontWeight: 600, letterSpacing: 0, marginBottom: 12 }}>
      {children}
    </div>
  );
}

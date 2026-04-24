import { C } from '../theme';

export default function SLabel({ children }) {
  return (
    <div style={{ fontSize: 11, color: C.inkFaint, fontFamily: 'Noto Sans SC', fontWeight: 300, letterSpacing: '.12em', marginBottom: 10 }}>
      {children}
    </div>
  );
}

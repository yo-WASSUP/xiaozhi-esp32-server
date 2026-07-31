import { House } from 'lucide-react';
import AppIcon from '../components/AppIcon';

export default function ComingSoonScreen({ appId, title, onHome }) {
  return (
    <div className={`coming-soon coming-soon--${appId}`}>
      <AppIcon appId={appId} className="coming-soon__mark" />
      <div className="coming-soon__kicker">{title}</div>
      <h1>功能开发中</h1>
      <p>这项服务正在认真准备，很快会和您见面。</p>
      <button type="button" onClick={onHome}>
        <House size={22} aria-hidden="true" />
        返回主菜单
      </button>
    </div>
  );
}

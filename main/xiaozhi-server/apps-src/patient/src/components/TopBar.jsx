import { useEffect, useState } from 'react';
import { House } from 'lucide-react';

function Clock() {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const hh = String(now.getHours()).padStart(2, '0');
  const mm = String(now.getMinutes()).padStart(2, '0');
  const period = now.getHours() < 6
    ? '凌晨'
    : now.getHours() < 12
      ? '上午'
      : now.getHours() < 18
        ? '下午'
        : '晚上';

  return (
    <div className="patient-topbar__clock" aria-label={`现在时间 ${hh}:${mm}`}>
      <strong>{hh}:{mm}</strong>
      <span>{period}</span>
    </div>
  );
}

export default function TopBar({
  activeApp,
  appTitle,
  connected,
  recording,
  micOk,
  connectStatus,
  onHome,
}) {
  const isVoicePage = activeApp === 'voice' || activeApp === 'dignity';

  const status = !isVoicePage
    ? { label: '系统待机', type: 'ready' }
    : recording
    ? { label: activeApp === 'dignity' ? '访谈正在进行' : '语音通话中', type: 'active' }
    : connected
      ? { label: isVoicePage ? '语音服务已就绪' : '系统已就绪', type: 'ready' }
      : { label: '语音服务连接中', type: 'waiting' };

  return (
    <header className="patient-topbar">
      <div className="patient-topbar__start">
        {activeApp === 'home' ? (
          <div className="patient-brand">
            <span className="patient-brand__mark" aria-hidden="true">暖</span>
            <span>
              <strong>安安</strong>
              <small>安宁疗护陪伴助手</small>
            </span>
          </div>
        ) : (
          <>
            <button className="patient-topbar__home" type="button" onClick={onHome} title="返回主菜单">
              <House size={24} strokeWidth={1.9} aria-hidden="true" />
              <span>主菜单</span>
            </button>
            <div className="patient-topbar__divider" />
            <div className="patient-topbar__title">{appTitle}</div>
          </>
        )}
      </div>

      <div className="patient-topbar__end">
        <div className={`patient-topbar__status patient-topbar__status--${status.type}`}>
          <span aria-hidden="true" />
          {status.label}
        </div>
        {isVoicePage && !micOk && (
          <div className="patient-topbar__notice">需要麦克风权限</div>
        )}
        {isVoicePage && connectStatus && connected && (
          <div className="patient-topbar__notice patient-topbar__notice--truncate">{connectStatus}</div>
        )}
        <Clock />
      </div>
    </header>
  );
}

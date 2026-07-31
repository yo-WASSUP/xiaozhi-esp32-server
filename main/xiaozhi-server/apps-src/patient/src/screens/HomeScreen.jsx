import { ChevronRight } from 'lucide-react';
import AppIcon from '../components/AppIcon';
import RobotAvatar from '../components/RobotAvatar';

export const APP_ITEMS = [
  {
    id: 'voice',
    title: '语音沟通',
    subtitle: '和小暖说说话',
  },
  {
    id: 'family',
    title: '家属消息',
    subtitle: '查看家人的问候',
  },
  {
    id: 'dignity',
    title: '尊严疗法',
    subtitle: '记录珍贵的人生故事',
  },
  {
    id: 'digital',
    title: '数字疗法',
    subtitle: '身心练习与陪伴',
    pending: true,
  },
  {
    id: 'aroma',
    title: '芳香疗法',
    subtitle: '舒缓身心的香气体验',
    pending: true,
  },
  {
    id: 'smartbed',
    title: '智能床联动',
    subtitle: '调节更舒适的姿势',
    pending: true,
  },
];

export const APP_TITLES = Object.fromEntries(APP_ITEMS.map(item => [item.id, item.title]));

function greeting() {
  const hour = new Date().getHours();
  if (hour < 6) return '夜深了，慢慢来';
  if (hour < 12) return '上午好';
  if (hour < 18) return '下午好';
  return '晚上好';
}

export default function HomeScreen({ unread = 0, onOpenApp }) {
  return (
    <div className="patient-home">
      <section className="patient-home__intro" aria-labelledby="home-title">
        <div className="patient-home__panda" aria-hidden="true">
          <div className="patient-home__panda-scale">
            <RobotAvatar state="idle" />
          </div>
        </div>
        <div className="patient-home__welcome">
          <div className="patient-home__eyebrow">小暖陪伴空间</div>
          <h1 id="home-title">{greeting()}，今天想先做什么？</h1>
        </div>
      </section>

      <section className="patient-home__apps" aria-labelledby="app-menu-title">
        <div className="patient-home__section-head">
          <h2 id="app-menu-title">常用服务</h2>
          <span>6 项</span>
        </div>
        <nav className="patient-app-grid" aria-label="应用菜单">
          {APP_ITEMS.map((item) => {
            const badge = item.id === 'family' && unread > 0 ? Math.min(unread, 99) : null;
            return (
              <button
                className="patient-app-card"
                key={item.id}
                type="button"
                onClick={() => onOpenApp(item.id)}
                aria-label={`打开${item.title}`}
              >
                <AppIcon appId={item.id} className="patient-app-card__icon" />
                <span className="patient-app-card__copy">
                  <strong>{item.title}</strong>
                  <span>{item.subtitle}</span>
                </span>
                {badge !== null && <span className="patient-app-card__badge">{badge}</span>}
                {item.pending && <span className="patient-app-card__status">开发中</span>}
                <ChevronRight className="patient-app-card__arrow" size={20} aria-hidden="true" />
              </button>
            );
          })}
        </nav>
      </section>
    </div>
  );
}

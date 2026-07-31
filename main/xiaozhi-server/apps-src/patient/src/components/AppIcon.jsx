import iconSprite from '../assets/app-icons/app-icon-sprite.webp';

const ICON_POSITIONS = {
  voice: '0% 0%',
  family: '50% 0%',
  dignity: '100% 0%',
  digital: '0% 100%',
  aroma: '50% 100%',
  smartbed: '100% 100%',
};

export default function AppIcon({ appId, className = '' }) {
  return (
    <span
      className={`app-illustration ${className}`.trim()}
      style={{
        backgroundImage: `url(${iconSprite})`,
        backgroundPosition: ICON_POSITIONS[appId] || ICON_POSITIONS.voice,
      }}
      aria-hidden="true"
    />
  );
}

import { useTheme } from '../context/ThemeContext.jsx'
import './Header.css'

export default function Header({ onMenuClick }) {
  const { theme, toggleTheme } = useTheme()

  return (
    <header className="ar-header">
      <div className="ar-header-left">
        <button className="ar-menu-btn" onClick={onMenuClick} aria-label="Toggle sidebar">
          ☰
        </button>
        <div className="ar-logo">
          <span className="ar-logo-mark">✦</span>
          <div className="ar-logo-text">
            <span className="ar-logo-title gradient-text">Debate Arena</span>
            <span className="ar-logo-sub">Elena vs. Marcus, evidence-driven</span>
          </div>
        </div>
      </div>

      <button
        className="ar-theme-toggle"
        onClick={toggleTheme}
        aria-label="Toggle dark mode"
        title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
      >
        <span className={`ar-theme-icon ${theme}`}>{theme === 'light' ? '☀️' : '🌙'}</span>
      </button>
    </header>
  )
}

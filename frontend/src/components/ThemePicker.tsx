import { useEffect, useRef, useState } from 'react'
import { THEMES, THEME_GROUPS, useTheme } from '../theme/ThemeProvider'

function auditCurrentTheme(): { label: string; ratio: number; ok: boolean }[] {
  const checks = [
    ['正文/画布', '--ink', '--canvas'],
    ['正文/面板', '--ink', '--surface'],
    ['表单文字', '--control-ink', '--control-bg'],
    ['侧栏文字', '--sidebar-ink', '--sidebar-bg'],
    ['侧栏次要文字', '--sidebar-muted', '--sidebar-bg'],
  ]
  const parseRgb = (value: string) => {
    const numbers = String(value).match(/[\d.]+/g)
    return numbers && numbers.length >= 3 ? numbers.slice(0, 3).map(Number) : null
  }
  const resolveColor = (variable: string) => {
    const probe = document.createElement('span')
    probe.style.cssText = `position:fixed;visibility:hidden;color:var(${variable})`
    document.body.appendChild(probe)
    const color = parseRgb(getComputedStyle(probe).color)
    probe.remove()
    return color
  }
  const luminance = (color: number[]) => {
    const values = color.map((item) => {
      const channel = item / 255
      return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
    })
    return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2]
  }
  return checks.map(([label, foreground, background]) => {
    const left = resolveColor(foreground)
    const right = resolveColor(background)
    let ratio = 0
    if (left && right) {
      const a = luminance(left)
      const b = luminance(right)
      ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
    }
    return { label, ratio, ok: ratio >= 4.5 }
  })
}

export function ThemePicker() {
  const { theme, accentHue, setTheme, setAccent } = useTheme()
  const [open, setOpen] = useState(false)
  const [audit, setAudit] = useState<{ label: string; ratio: number; ok: boolean }[]>([])
  const pickerRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const indexRef = useRef(Math.floor(Math.random() * 1000))

  const activeTheme = THEMES.find((item) => item.id === theme) || THEMES[0]

  useEffect(() => {
    if (!open) return
    const menu = menuRef.current
    if (!menu) return
    const sidebar = pickerRef.current?.closest('.sidebar') as HTMLElement | null
    if (sidebar) {
      const sidebarRect = sidebar.getBoundingClientRect()
      const pickerRect = pickerRef.current!.getBoundingClientRect()
      const paddingLeft = Number.parseFloat(getComputedStyle(sidebar).paddingLeft) || 0
      const paddingRight = Number.parseFloat(getComputedStyle(sidebar).paddingRight) || 0
      const menuWidth = menu.getBoundingClientRect().width
      const minLeft = sidebarRect.left + paddingLeft - pickerRect.left
      const maxLeft = sidebarRect.right - paddingRight - menuWidth - pickerRect.left
      menu.style.left = `${Math.max(minLeft, maxLeft)}px`
      menu.style.right = 'auto'
    }
    setAudit(auditCurrentTheme())
  }, [open, theme, accentHue])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    const onClickOutside = (event: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('click', onClickOutside)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('click', onClickOutside)
    }
  }, [])

  const failures = audit.filter((check) => !check.ok)

  return (
    <div className="theme-picker" data-theme-picker ref={pickerRef}>
      <button
        className="theme-picker-button"
        type="button"
        title={`切换界面主题，当前：${activeTheme.name}`}
        aria-label={`切换界面主题，当前：${activeTheme.name}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation()
          setOpen((value) => !value)
        }}
      >
        <span aria-hidden="true">◐</span>
      </button>
      <div className={`theme-menu ${open ? '' : 'hidden'}`} role="menu" aria-label="界面主题" ref={menuRef}>
        {THEME_GROUPS.map((group) => (
          <section className="theme-group" key={group.id}>
            <p className="theme-group-title">{group.name}</p>
            {THEMES.filter((item) => item.group === group.id).map((item) => {
              const active = item.id === theme
              return (
                <button
                  key={item.id}
                  className={`theme-option ${active ? 'active' : ''}`}
                  type="button"
                  role="menuitemradio"
                  aria-checked={active}
                  data-theme-option={item.id}
                  onClick={() => {
                    setTheme(item.id, { account: true })
                    setOpen(false)
                  }}
                >
                  <span className="theme-swatches" aria-hidden="true">
                    <i style={{ background: item.colors[0] }}></i>
                    <i style={{ background: item.colors[1] }}></i>
                  </span>
                  <span>{item.name}</span>
                  <b aria-hidden="true">✓</b>
                  <em className="theme-option-warning" aria-label="对比度未通过" />
                </button>
              )
            })}
          </section>
        ))}
        <section className="theme-custom">
          <div className="theme-custom-head">
            <label htmlFor={`theme-hue-${indexRef.current}`}>自定义强调色</label>
            <button type="button" data-theme-accent-reset disabled={accentHue === null} onClick={() => setAccent(null, { account: true })}>
              恢复默认
            </button>
          </div>
          <div className="theme-custom-row">
            <input
              id={`theme-hue-${indexRef.current}`}
              data-theme-hue
              type="range"
              min="0"
              max="359"
              step="1"
              value={accentHue ?? activeTheme.hue}
              onChange={(event) => setAccent(Number(event.target.value), { account: true })}
            />
            <span className="theme-accent-preview" aria-hidden="true" />
          </div>
          <p className={`theme-audit ${failures.length ? 'warning' : ''}`} data-theme-audit aria-live="polite">
            {failures.length
              ? `AA 注意：${failures.map((item) => `${item.label} ${item.ratio.toFixed(1)}:1`).join('、')}`
              : 'WCAG AA 核心文字对比度通过'}
          </p>
        </section>
      </div>
    </div>
  )
}
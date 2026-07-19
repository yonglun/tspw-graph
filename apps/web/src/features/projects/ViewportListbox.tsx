import {
  type CSSProperties,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'
import { createPortal } from 'react-dom'

import { type ListboxPlacement, placeListbox } from './listboxPosition'

export type ViewportListboxOption = {
  value: string
  label: string
}

type ViewportListboxProps = {
  label: string
  value: string
  options: ViewportListboxOption[]
  disabled?: boolean
  disabledTitle?: string
  dismissSignal?: string
  onChange: (value: string) => void
}

const optionHeight = 40

export function ViewportListbox({
  label,
  value,
  options,
  disabled = false,
  disabledTitle,
  dismissSignal,
  onChange,
}: ViewportListboxProps) {
  const listboxId = useId()
  const triggerRef = useRef<HTMLButtonElement>(null)
  const listboxRef = useRef<HTMLUListElement>(null)
  const optionRefs = useRef<Array<HTMLLIElement | null>>([])
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const [position, setPosition] = useState<ListboxPlacement | null>(null)
  const selectedIndex = Math.max(0, options.findIndex(option => option.value === value))
  const selected = options[selectedIndex]

  const close = useCallback((restoreFocus = false) => {
    setOpen(false)
    setPosition(null)
    if (restoreFocus) {
      triggerRef.current?.focus()
    }
  }, [])

  const show = () => {
    if (disabled || options.length === 0) return
    setActiveIndex(selectedIndex)
    setOpen(true)
  }

  const choose = (index: number) => {
    const option = options[index]
    if (!option) return
    if (option.value !== value) onChange(option.value)
    close(true)
  }

  useLayoutEffect(() => {
    if (!open || !triggerRef.current) return
    const trigger = triggerRef.current.getBoundingClientRect()
    setPosition(
      placeListbox(
        trigger,
        { width: window.innerWidth, height: window.innerHeight },
        Math.min(options.length * optionHeight + 8, 320),
      ),
    )
  }, [open, options.length])

  useEffect(() => {
    if (!open || !position) return
    optionRefs.current[activeIndex]?.focus()
  }, [activeIndex, open, position])

  useEffect(() => {
    if (!open) return

    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node
      if (!triggerRef.current?.contains(target) && !listboxRef.current?.contains(target)) close()
    }
    const onViewportChange = () => close()

    document.addEventListener('pointerdown', onPointerDown)
    window.addEventListener('resize', onViewportChange)
    window.addEventListener('scroll', onViewportChange, true)
    window.addEventListener('popstate', onViewportChange)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      window.removeEventListener('resize', onViewportChange)
      window.removeEventListener('scroll', onViewportChange, true)
      window.removeEventListener('popstate', onViewportChange)
    }
  }, [close, open])

  useEffect(() => {
    setOpen(false)
    setPosition(null)
  }, [value])

  useEffect(() => {
    setOpen(false)
    setPosition(null)
  }, [dismissSignal])

  const onTriggerKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      show()
    }
  }

  const onListboxKeyDown = (event: KeyboardEvent<HTMLUListElement>) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex(index => Math.min(options.length - 1, index + 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex(index => Math.max(0, index - 1))
    } else if (event.key === 'Home') {
      event.preventDefault()
      setActiveIndex(0)
    } else if (event.key === 'End') {
      event.preventDefault()
      setActiveIndex(options.length - 1)
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      choose(activeIndex)
    } else if (event.key === 'Escape') {
      event.preventDefault()
      close(true)
    } else if (event.key === 'Tab') {
      close()
    }
  }

  const listboxStyle: CSSProperties | undefined = position
    ? {
        top: position.top,
        left: position.left,
        width: position.width,
        maxHeight: position.maxHeight,
      }
    : undefined

  return (
    <div className="viewport-listbox">
      <button
        ref={triggerRef}
        type="button"
        className="viewport-listbox__trigger"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listboxId : undefined}
        disabled={disabled}
        title={disabled ? disabledTitle : undefined}
        onClick={() => (open ? close() : show())}
        onKeyDown={onTriggerKeyDown}
      >
        <span className="viewport-listbox__value">{selected?.label ?? ''}</span>
        <svg aria-hidden="true" viewBox="0 0 16 16" width="16" height="16">
          <path d="m4 6 4 4 4-4" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && position && createPortal(
        <ul
          ref={listboxRef}
          id={listboxId}
          className="viewport-listbox__menu"
          style={listboxStyle}
          role="listbox"
          aria-label={label}
          aria-activedescendant={`${listboxId}-option-${activeIndex}`}
          onKeyDown={onListboxKeyDown}
        >
          {options.map((option, index) => (
            <li
              key={option.value}
              ref={node => { optionRefs.current[index] = node }}
              id={`${listboxId}-option-${index}`}
              className="viewport-listbox__option"
              role="option"
              aria-selected={option.value === value}
              tabIndex={index === activeIndex ? 0 : -1}
              data-active={index === activeIndex || undefined}
              onClick={() => choose(index)}
              onMouseMove={() => setActiveIndex(index)}
            >
              <span className="viewport-listbox__check" aria-hidden="true">
                {option.value === value ? '✓' : ''}
              </span>
              <span>{option.label}</span>
            </li>
          ))}
        </ul>,
        document.body,
      )}
    </div>
  )
}

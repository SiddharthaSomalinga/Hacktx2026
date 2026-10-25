import type { ButtonHTMLAttributes } from 'react'
import styles from './Button.module.css'

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'quiet' | 'danger'
  block?: boolean
}

export function Button({ variant = 'secondary', block = false, className, type = 'button', ...rest }: Props) {
  const classes = [styles.button, styles[variant], block ? styles.block : '', className ?? ''].join(' ')
  return <button type={type} className={classes} {...rest} />
}

export function IconButton({ className, type = 'button', ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type={type} className={[styles.button, styles.icon, className ?? ''].join(' ')} {...rest} />
}

import { Children, cloneElement, isValidElement } from 'react'

/**
 * Container whose direct children fade up one after another (staggered via the `--i` CSS variable).
 * Non-element children (null, false, strings) are passed through untouched.
 */
export default function ResultCards({ className = '', children }) {
  let n = 0
  return (
    <div className={className}>
      {Children.map(children, (child) => {
        if (!isValidElement(child)) return child
        const i = n++
        return cloneElement(child, {
          className: `${child.props.className ?? ''} rc`.trim(),
          style: { ...child.props.style, '--i': i },
        })
      })}
    </div>
  )
}

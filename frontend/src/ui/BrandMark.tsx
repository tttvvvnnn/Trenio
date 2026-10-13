// Знак Trenio (секундомер). Корпус берёт цвет текста темы Telegram, сектор всегда коралловый.
// Пути совпадают с assets/brand/trenio-mark.svg.
export default function BrandMark({
  size = 64,
  spinning = false,
}: {
  size?: number
  spinning?: boolean
}) {
  return (
    <svg
      className={spinning ? 'brand-mark spinning' : 'brand-mark'}
      viewBox="14 2 72 96"
      width={size * 0.75}
      height={size}
      aria-hidden="true"
    >
      <path
        fill="currentColor"
        d="M32 4H68A3 3 0 0 1 71 7V13A3 3 0 0 1 68 16H32A3 3 0 0 1 29 13V7A3 3 0 0 1 32 4Z M43 12H57V31H43Z M75.29 23.64L82.36 30.71L76.71 36.36L69.64 29.29Z M17 62A33 33 0 1 1 83 62A33 33 0 1 1 17 62Z"
      />
      <path className="brand-mark-sector" fill="#FF5A36" d="M50 62L50 38A24 24 0 0 1 70.78 74Z" />
      <circle cx="50" cy="62" r="4" fill="currentColor" />
    </svg>
  )
}

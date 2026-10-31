/** Fixed, slowly morphing mesh of blurred colour blobs behind the whole app (pure CSS, GPU transforms only). */
export default function AmbientBackground() {
  return (
    <div className="ambient" aria-hidden="true">
      <i className="blob b1" />
      <i className="blob b2" />
      <i className="blob b3" />
      <i className="blob b4" />
      <i className="ambient-grid" />
    </div>
  )
}

// Demo inputs for one-click testing.
export const PRESETS = [
  {
    id: 'verified',
    icon: '🟢',
    tone: 'good',
    label: 'Reuters Official Press Release',
    url: 'https://www.reuters.com/business/',
    text:
      'LONDON (Reuters) - The Bank of England held interest rates steady on Thursday, citing stable inflation and moderate wage growth, ' +
      'according to a statement released after the Monetary Policy Committee meeting. Five members voted to hold and ' +
      'four voted for a cut, and economists surveyed by Reuters said they expect a cut later this year.',
  },
  {
    id: 'rumor',
    icon: '🔴',
    tone: 'bad',
    label: '5G Microchip Viral Conspiracy',
    text:
      'URGENT!!! Forward this to 10 people. 5G towers are spreading the coronavirus through secret microchips and the government is hiding the ' +
      'shocking truth from you!!! NASA confirms six days of total darkness next week, a trusted source told us. Share now before they delete this!!!',
  },
  {
    id: 'gossip',
    icon: '🟡',
    tone: 'warn',
    label: 'Clickbait Celebrity Gossip',
    url: 'https://celeb-leaks-daily.xyz/shocking',
    text:
      "You won't believe what this A-list star was caught doing at 3AM! Fans are SPEECHLESS. Insiders reveal the shocking secret scandal " +
      'the tabloids tried to hide. Doctors HATE this one weird trick for looking 20 years younger. Click here now to see the leaked photos before they get deleted!!!',
  },
]

/** Draws a fake newspaper clipping on a canvas and returns it as a PNG File. */
export function makeNewspaperClip() {
  const c = document.createElement('canvas')
  c.width = 1100
  c.height = 700
  const g = c.getContext('2d')
  g.fillStyle = '#f5f1e6'
  g.fillRect(0, 0, c.width, c.height)
  g.fillStyle = '#111'
  g.textBaseline = 'top'
  g.font = 'bold 40px Georgia, serif'
  g.fillText('THE DAILY TRUTH', 60, 40)
  g.fillRect(60, 100, 980, 4)
  g.font = 'bold 66px Georgia, serif'
  g.fillText('SHOCKING SECRET EXPOSED:', 60, 130)
  g.fillText('5G Towers Spread Virus', 60, 210)
  g.font = '34px Georgia, serif'
  const body = [
    "You won't believe what the government is hiding.",
    'A whistleblower says the miracle cover-up is finally',
    'exposed and the media is silent. Share this now',
    'before it is deleted!!! Officials deny nothing.',
  ]
  body.forEach((l, i) => g.fillText(l, 60, 330 + i * 56))
  return new Promise((resolve, reject) =>
    c.toBlob((b) => (b ? resolve(new File([b], 'newspaper-clip-sample.png', { type: 'image/png' })) : reject(new Error('Canvas export failed'))), 'image/png'),
  )
}

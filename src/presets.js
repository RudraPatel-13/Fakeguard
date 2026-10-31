// Demo inputs for one-click testing.
export const PRESETS = [
  {
    id: 'verified',
    label: 'Try Verified News (BBC/AP)',
    url: 'https://www.bbc.com/news/business',
    text:
      'The Bank of England held interest rates steady on Thursday, citing stable inflation and moderate wage growth, ' +
      'according to a statement released after the Monetary Policy Committee meeting. Five members voted to hold and ' +
      'four voted for a cut, and economists surveyed by Reuters said they expect a cut later this year.',
  },
  {
    id: 'scam',
    label: 'Try Viral Clickbait Scam',
    url: 'https://breaking-tech-truth-daily.xyz/free-phone',
    text:
      "You won't believe this! Shocking secret trick banned by Big Tech: get a FREE iPhone today!!! " +
      'Whistleblower exposed the scam that banks hate. Doctors HATE this one weird trick. ' +
      'Click here now, the offer is a limited miracle and will be deleted soon!!!',
  },
  {
    id: 'rumor',
    label: 'Try Sensational Social Media Rumor',
    text:
      'URGENT!!! Forward this to 10 people. 5G towers are spreading the coronavirus and the government is hiding the ' +
      'shocking truth from you!!! NASA confirms six days of total darkness next week, a trusted source told us. Share now before they delete this!!!',
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

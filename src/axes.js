export const AXES = [
  ['sensationalism', 'Sensationalism', 'Share of the suspicious-keyword budget used (direct keywords + WordNet synonyms). Higher = more sensational vocabulary.'],
  ['clickbait', 'Clickbait', 'Share of the clickbait-phrase budget used (e.g. "you won\'t believe").'],
  ['emotional_manipulation', 'Emotional Manipulation', 'Excess capitalisation, exclamation and question marks relative to their maximum rule points.'],
  ['source_risk', 'Source Credibility Risk', '100 minus the publisher trust score from the bundled registry/heuristics. Needs a URL; n/a otherwise.'],
  ['ml_risk', 'ML Classifier Risk', '100 minus the ML credible-style probability. A stylistic signal from a small seed-trained model, not a fact check.'],
  ['corroboration_risk', 'Web Corroboration Risk', '100 minus the live-web corroboration score: how little reputable coverage supports the claim. n/a when web search was not run or unavailable.'],
  ['forensic_risk', 'Forensic Tampering Risk', 'Heuristic from ELA discrepancy + EXIF editing traces. Image scans only. Not proof of tampering.'],
]


"""Mechanical grounding checks: these are not a general semantic entailment test."""
import re
from collections import Counter

NUMBER = re.compile(r'(?<![A-Za-z0-9])[-+]?\$?\d[\d,]*(?:\.\d+)?%?')
CAUSE = re.compile(r'\b(because|due to|driven by|caused by|consumer demand|promotion|seasonal demand)\b', re.I)


def contract(r, facts, forecast, lead):
    nxt = forecast['next_month']
    facts = dict(facts)
    facts['forecast'] = (f"For {nxt['target'][:7]}, seasonal naive forecasts {nxt['seasonal_naive']:,.0f} net bottles; "
                         f"Holt-Winters forecasts {nxt['holt_winters']:,.0f} net bottles.")
    ids = list(dict.fromkeys([lead, 'quality', 'sales' if 'sales' in facts else lead, 'forecast']))
    return {i:facts[i] for i in ids}


def checks(expected, result):
    if not isinstance(result, dict) or set(expected)!=set(result):
        return {'schema':False}
    def numbers(s):
        return Counter(n.replace(',','') for n in NUMBER.findall(s))
    scores={'schema':True}
    for key, source in expected.items():
        s=result[key]
        if not isinstance(s,str) or not 8<=len(s)<=600:
            scores[key+'.text']=False
            continue
        scores[key+'.numbers']=numbers(s)==numbers(source)
        scores[key+'.no_unverified_cause']=not CAUSE.search(s)
        if key=='quality':
            status=re.search(r'status: (\w+)',source).group(1)
            scores['quality.status']=status in s
            scores['quality.unavailable']=('unavailable' not in source.lower() or 'unavailable' in s.lower())
        if key=='forecast':
            # Check number-to-method binding, not only the unordered set of values.
            for method in ('seasonal naive','Holt-Winters'):
                def binding(line):
                    m=re.search(re.escape(method)+r'[^\d;]{0,55}(\d[\d,]*)',line,re.I)
                    return m.group(1).replace(',','') if m else None
                scores[method+'.value']=binding(s)==binding(source)
            scores['forecast.modality']=bool(re.search(r'forecast|project|expect|estimate',s,re.I))
        if key=='yoy':
            # Permit only an unambiguous sales YoY sentence when replacing a numeric sign.
            # Full matching avoids accepting negation, the wrong metric, or a monthly comparison.
            pct = next(n for n in NUMBER.findall(source) if n.endswith('%'))
            magnitude = re.escape(pct.lstrip('+-'))
            verb = 'increased|rose|grew' if pct.startswith('+') else 'decreased|fell|declined'
            verbal = re.fullmatch(
                rf'(?:reported )?(?:distribution )?sales (?:have |had )?(?:{verb}) (?:by )?{magnitude} '
                r'(?:compared to|compared with|versus) the same (?:calendar month|month|period) last year[.]?',
                s.strip(), re.I)
            literal = s.strip().casefold() == source.strip().casefold()
            scores['yoy.direction'] = bool(literal or verbal)
            scores['yoy.numbers'] = scores['yoy.numbers'] or bool(verbal)
    return scores

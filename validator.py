"""Loss-aware TSV parser and optional business schema mapping."""
import csv
import io
import re
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from pathlib import Path
from schema import STANDARD_COLUMNS, COLUMN_ALIASES

MISSING = {'', 'n/a', 'na', 'none', 'unknown', 'not available', '-'}

def norm(s):
    return ''.join(c for c in s.casefold() if c.isalnum())

def missing(s): return s.strip().casefold() in MISSING

def signals(s):
    s = s.strip()
    if missing(s): return set()
    kinds = set()
    if re.fullmatch(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}',s): kinds.add('date')
    if re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',s): kinds.add('email')
    if re.match(r'https?://|www\.',s,re.I): kinds.add('web')
    if re.fullmatch(r'\d{5}(?:-\d{4})?',s): kinds.add('zip')
    if re.fullmatch(r'[A-Z]{2}',s): kinds.add('state')
    if re.fullmatch(r'[+()\d .-]+(?:\s*(?:ext\.?|x)\s*\d+)?',s,re.I) and 10<=len(re.sub(r'\D','',s))<=18: kinds.add('phone')
    if re.match(r'^(yes|no)\b',s,re.I): kinds.add('emergency')
    elif re.search(r'\b(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)\b|\b(?:AM|PM)\b|24\s*(?:hours?|/7)|by appointment|\bclosed\b',s,re.I): kinds.add('hours')
    if re.search(r',\s*(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b',s): kinds.add('geo')
    if re.search(r'\bcounty\b',s,re.I): kinds.add('county')
    if re.match(r'^(?:\d+\s|P\.?\s*O\.?\s*Box\b)',s,re.I): kinds.add('address')
    if re.search(r'\b(?:insured|insurance|bonded|liability)\b',s,re.I): kinds.add('insurance')
    if re.search(r'electrical|wiring|installations?|generators?|lighting|remodel|automation|contracting|chargers?|engineering|equipment|repairs?|plumbing|roofing|cleaning|maintenance',s,re.I) : kinds.add('service')
    return kinds

TYPES = {'LicIssuedOn':'date','LicExpiresOn':'date','LicVerifiedOn':'date','InsVerifiedOn':'date','LastResearchedOn':'date','AddrZipCode':'zip','AddrState':'state','Email':'email','Website':'web','Phone':'phone','EmergencyNumber':'phone','Hours':'hours','EmergencyAvailability':'emergency','InsType':'insurance','ServiceSpecialities':'service','ServiceAreas':'geo','Locations':'geo','AddrLine1':'address','AddrLine2':'address','AddrCounty':'county'}
STRONG = {'date','email','web','zip','phone','hours','emergency'}
STRICT = {'date','email','web','zip','phone','hours','emergency','state'}

def score(value, header, kinds):
    if missing(value): return 0
    typ = TYPES.get(header)
    if typ in kinds: return 9 if typ in STRICT else (6.5 if header=='ServiceAreas' else 5)
    if typ in STRICT and kinds & STRONG: return -13
    if typ in STRICT: return -3
    if kinds & STRONG: return -8
    if header=='ServiceSpecialities' and 'geo' in kinds and 'service' not in kinds: return -6
    if header in ('ServiceAreas','Locations') and 'service' in kinds: return -5
    if header in ('AddrLine1','AddrLine2','AddrCity') and ('geo' in kinds or 'address' in kinds): return 1
    return 0

def suspicious(row, headers):
    for v,h in zip(row,headers):
        if missing(v): continue
        k = signals(v); t=TYPES.get(h)
        if t in STRICT and k & STRONG and t not in k: return True
        if h=='AddrZipCode' and 'zip' not in k: return True
        if h in ('ServiceAreas','Locations') and 'service' in k and 'geo' not in k: return True
        if h=='ServiceSpecialities' and 'geo' in k and 'service' not in k: return True
        if h in ('ServiceAreas','Locations','AddrLine1','AddrLine2','AddrCity','InsType','ServiceSpecialities') and k & {'hours','email','web','phone'}: return True
    return False

def suggest_alignment(raw, headers):
    """Bounded dynamic programming: insert blanks or remove empty placeholders only.
    Return source-index mapping, never silently remove a nonempty field. All suggestions need approval.
    """
    n,m=len(raw),len(headers)
    if n>65 or m>40 or abs(n-m)>12: return None
    kinds=[signals(v) for v in raw]
    # Keep two distinct value layouts at each state, favour positional preservation.
    dp={(0,0):[(0,(),())]}
    def put(i,j,s,indices,vals):
        bucket=dp.setdefault((i,j),[])
        for p,x in enumerate(bucket):
            if x[2]==vals:
                if x[0]>=s: return
                bucket.pop(p); break
        bucket.append((s,indices,vals)); bucket.sort(key=lambda x:x[0],reverse=True)
        del bucket[2:]
    for i in range(n+1):
        for j in range(m+1):
            for s,idx,vals in dp.get((i,j),[])[:]:
                if i<n and j<m:
                    # Exact prefix is valuable; semantic anchors can outweigh displacement.
                    put(i+1,j+1,s+score(raw[i],headers[j],kinds[i])-(0 if i==j else .12),idx+(i,),vals+(raw[i],))
                if j<m: put(i,j+1,s-2,idx+(None,),vals+('',))
                if i<n and raw[i]=='': put(i+1,j,s-2,idx,vals)
    final=dp.get((n,m),[])
    if not final: return None
    s,idx,vals=final[0]
    if n==m and tuple(raw)==vals: return None
    if n==m:
        base=sum(score(v,h,k) for v,h,k in zip(raw,headers,kinds))
        if s<base+4: return None
    # Close alternatives are still displayed but labelled ambiguous.
    ambiguous=len(final)>1 and s-final[1][0]<4
    return list(idx),ambiguous

def read_text(path):
    data=Path(path).read_bytes()
    if data.startswith((b'\xff\xfe',b'\xfe\xff')): return data.decode('utf-16')
    return data.decode('utf-8-sig')

def validate_tsv(file_path=None,text=None,mode='business',header_override=None):
    result={'valid':False,'errors':[],'warnings':[],'headers':[],'source_headers':[],'accepted':[],'rows':[],'review':[],'mode':mode,'extra_columns':[]}
    try:
        if mode not in ('business','general'): raise ValueError('Unknown conversion mode.')
        content=read_text(file_path) if file_path is not None else text
        if content is None: raise ValueError('No input provided.')
        content=content.removeprefix('\ufeff')
        lines=content.splitlines(keepends=True)
        nonblank=[i for i,v in enumerate(lines) if v.strip()]
        if len(nonblank)>=2 and re.fullmatch(r'```(?:tsv|txt|text|less)?',lines[nonblank[0]].strip(),re.I) and lines[nonblank[-1]].strip()=='```':
            for i in (nonblank[0],nonblank[-1]): lines[i]='\n' if lines[i].endswith('\n') else ''
            content=''.join(lines); result['warnings'].append('Outer Markdown fence removed.')
        stream=io.StringIO(content,newline=''); reader=csv.reader(stream,delimiter='\t',strict=True)
        headers=next((r for r in reader if r and any(v.strip() for v in r)),None)
        if headers is None: raise ValueError('No header row found.')
        result['source_headers']=headers[:]; result['header_line']=reader.line_num
        lookup={norm(c):c for c in STANDARD_COLUMNS}; lookup.update({norm(a):c for a,c in COLUMN_ALIASES.items()})
        if mode=='general':
            out=headers[:]; mapping=list(range(len(headers)))
        else:
            out=STANDARD_COLUMNS[:]; mapping=[None]*len(out); used=set()
            if header_override is not None:
                original,indices=header_override
                if original!=headers: raise ValueError('Input headers changed. Revalidate before mapping.')
                resolve_row({'raw':headers},indices,len(STANDARD_COLUMNS))
                mapping=list(indices); used={out[j] for j,i in enumerate(mapping) if i is not None}
            else:
                for i,h in enumerate(headers):
                    target=lookup.get(norm(h))
                    if target and target not in used:
                        mapping[out.index(target)]=i; used.add(target)
            assigned=set(mapping)
            for i,h in enumerate(headers):
                if i not in assigned:
                    out.append(f'Extra: {h or "Unnamed"} [field {i+1}]'); mapping.append(i); result['extra_columns'].append(len(out)-1)
            if result['extra_columns']: result['warnings'].append('Unrecognized or duplicate headers retained as highlighted extra columns.')
            if 'Name' not in used: result['warnings'].append('No recognized Name header. Check mapping or use General mode.')
            absent=[c for c in STANDARD_COLUMNS if c not in used]
            if absent: result['warnings'].append('Missing business columns left blank: '+', '.join(absent))
        result['headers']=out; result['source_mapping']=mapping
        def mapped(r): return [r[i] if i is not None and i<len(r) else '' for i in mapping]
        def mapped_idx(idx): return [idx[i] if i is not None and i<len(idx) else None for i in mapping]
        canonical=mode=='business' and mapping==list(range(len(STANDARD_COLUMNS))) and len(headers)==len(STANDARD_COLUMNS)
        while True:
            start=reader.line_num+1; offset=stream.tell()
            try: raw=next(reader)
            except StopIteration: break
            except csv.Error as e:
                # Broken quote may consume multiple physical lines. Keep the exact unparsed fragment, do not guess its records.
                end=stream.tell(); fragment=content[offset:end]
                result['review'].append({'line':start,'raw':[fragment],'reason':f'Malformed quoted TSV: {e}. Raw text retained.','mapping':None,'suggestion':None,'unparsed':True})
                if end>=len(content) or end<=offset: break
                reader=csv.reader(stream,delimiter='\t',strict=True)
                # Reader line numbers restart; preserve remaining text in same review item instead of mislabelling lines.
                result['review'][-1]['raw'][0]+=stream.read(); break
            if not raw: continue
            reason=''; idx=None
            if len(raw)!=len(headers): reason=f'Expected {len(headers)} fields, found {len(raw)}.'
            elif canonical and suspicious(raw,headers): reason='Possible semantic column shift.'
            if any(len(v.encode('utf-16-le'))//2>32767 or ILLEGAL_CHARACTERS_RE.search(v) for v in raw):
                result['review'].append({'line':start,'raw':raw,'reason':'A field exceeds Excel cell limits or contains unsupported controls; preserved in review.','mapping':None,'suggestion':None,'unparsed':True}); continue
            if reason:
                if canonical:
                    proposal=suggest_alignment(raw,headers)
                    if proposal:
                        indices,ambiguous=proposal; idx=mapped_idx(indices)
                        reason+=' Suggested blank-field alignment'+(' (ambiguous; check carefully).' if ambiguous else ' (review before approving).')
                if idx is None and len(raw)==len(headers): idx=mapped_idx(list(range(len(raw))))
                result['review'].append({'line':start,'raw':raw,'reason':reason,'mapping':idx,'suggestion':None if idx is None else [raw[i] if i is not None else '' for i in idx]})
            else:
                row=mapped(raw); result['accepted'].append({'line':start,'row':row}); result['rows'].append(row)
        if not result['accepted'] and not result['review']: raise ValueError('No data records found.')
        result['valid']=True
    except (OSError,UnicodeError,ValueError,csv.Error) as e: result['errors'].append(str(e))
    return result

def resolve_row(item, indices, columns, discard=False):
    """Explicit mapping decisions; every unassigned source value stays separate unless discarded by user."""
    raw=item['raw']; selected=[i for i in indices if i is not None]
    if len(indices)!=columns or len(selected)!=len(set(selected)) or any(not isinstance(i,int) or not 0<=i<len(raw) for i in selected): raise ValueError('Each original field may be mapped at most once.')
    extras=[(i+1,v) for i,v in enumerate(raw) if i not in selected]
    return {'row':[raw[i] if i is not None else '' for i in indices], 'extras':extras,'discard':bool(discard),'mapping':list(indices)}

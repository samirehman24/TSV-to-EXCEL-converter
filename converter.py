"""Excel writer with an audit trail and explicit extra-field decisions."""
import os
import tempfile
from pathlib import Path
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter
from validator import validate_tsv, resolve_row

MAX_ROWS=1048576
MAX_COLS=16384

def safe_text(v):
    s=str(v)
    if len(s.encode('utf-16-le'))//2>32767 or ILLEGAL_CHARACTERS_RE.search(s):
        raise ValueError('Excel cannot store a cell losslessly (too long or illegal control character). No existing output was changed.')
    return s

def export_result(result, output_path, decisions=None, extra_headers='keep'):
    if not result['valid']: raise ValueError('\n'.join(result['errors']))
    if extra_headers not in ('keep','separate','discard'): raise ValueError('Invalid extra-column policy.')
    decisions=decisions or {}
    valid_lines={r['line'] for r in result['review'] if not r.get('unparsed')}
    if set(decisions)-valid_lines: raise ValueError('Unknown or unparsed review row in decisions.')
    headers=result['headers']; extra=set(result['extra_columns']); keep=[i for i in range(len(headers)) if extra_headers=='keep' or i not in extra]
    data=[]; pending=[]; extras=[]; audit=[]; original=[]; suggestions=[]
    for r in result['accepted']: data.append((r['line'],r['row']))
    for r in result['review']:
        line=r['line']; decision=decisions.get(line)
        if decision is None:
            pending.append(r)
            if r['suggestion'] is not None:
                for i,v in enumerate(r['suggestion']): suggestions.append([line,i+1,headers[i],v])
            continue
        d=resolve_row(r,decision['mapping'],len(headers),decision.get('discard',False))
        data.append((line,d['row']))
        audit.append([line,'Approved mapping',r['reason']])
        for target,source in enumerate(d['mapping']):
            audit.append([line,f'Output {target+1}: {headers[target]}',f'Original field {source+1}' if source is not None else 'Inserted blank'])
        dropped={j for j,_ in d['extras']} if d['discard'] else set()
        for i,v in enumerate(r['raw'],1):
            if i in dropped:
                audit.append([line,f'Field {i}','Discarded by explicit user approval']); continue
            original.append([line,i,v])
        if not d['discard']:
            extras.extend([line,f'Original field {i}',v] for i,v in d['extras'])
    data.sort(key=lambda x:x[0])
    if extra_headers!='keep':
        omit_original=set()
        for line,row in data:
            for i in sorted(extra):
                if extra_headers=='separate': extras.append([line,headers[i],row[i]])
                # Do not retain explicitly discarded header values in original repair audit.
                else:
                    decision=decisions.get(line)
                    if decision and decision['mapping'][i] is not None:
                        source=decision['mapping'][i]+1
                        omit_original.add((line,source))
        if omit_original: original=[x for x in original if (x[0],x[1]) not in omit_original]
        audit.append(['','Extra header policy',extra_headers])
    wb=Workbook(write_only=True)
    green=PatternFill('solid',fgColor='217346'); yellow=PatternFill('solid',fgColor='FFF2CC'); white=Font(bold=True,color='FFFFFF'); dark=Font(bold=True,color='713F12'); align=Alignment(vertical='top',wrap_text=True)
    def sheet(name, hs, rows, highlighted=(), all_highlight=False):
        if not hs or len(hs)>MAX_COLS: raise ValueError(f'{name}: exceeds Excel column limit ({MAX_COLS}).')
        ws=None; count=MAX_ROWS; part=0
        def new():
            nonlocal ws,count,part
            part+=1; title=name if part==1 else f'{name[:24]} {part}'
            ws=wb.create_sheet(title); ws.freeze_panes='A2'
            for j,h in enumerate(hs,1): ws.column_dimensions[get_column_letter(j)].width=min(55,max(14,len(str(h))+3, 32 if 'value' in str(h).lower() else 0))
            count=1; append(hs,True)
        def append(row,head=False):
            cells=[]
            for j,v in enumerate(row):
                c=WriteOnlyCell(ws,value=safe_text(v)); c.data_type='s'; c.number_format='@'; c.alignment=align
                if head: c.fill=yellow if all_highlight or j in highlighted else green; c.font=dark if all_highlight or j in highlighted else white
                elif all_highlight or j in highlighted: c.fill=yellow
                cells.append(c)
            ws.append(cells)
        def finish():
            if ws is not None: ws.auto_filter.ref=f'A1:{get_column_letter(len(hs))}{count}'; ws.close()
        new()
        for row in rows:
            if count==MAX_ROWS: finish(); new()
            append(row); count+=1
        finish()
    # Audit fields stored in long form so arbitrary extra field counts do not overflow a sheet.
    # Escape only unsupported controls in review data and split large fields with explicit part numbers.
    def long_rows(rows):
        for line,field,value in rows:
            s=str(value); encoding='literal'
            if ILLEGAL_CHARACTERS_RE.search(s):
                import json
                s=json.dumps(s,ensure_ascii=True); encoding='JSON string'
            # 15000 codepoints <= 30000 UTF-16 units, even for astral chars.
            parts=[s[i:i+15000] for i in range(0,len(s),15000)] or ['']
            for i,p in enumerate(parts,1): yield [line,field,i,len(parts),encoding,p]
    output=Path(output_path).resolve()
    if output.suffix.lower()!='.xlsx': raise ValueError('Choose an .xlsx filename.')
    temp=None
    try:
        # Check clean cells before opening write-only streams.
        for h in [headers[i] for i in keep]: safe_text(h)
        for _,row in data:
            for i in keep: safe_text(row[i])
        sheet('Data',[headers[i] for i in keep],([row[i] for i in keep] for _,row in data),[j for j,i in enumerate(keep) if i in extra])
        sheet('Summary',['Item','Value'],[['Mode',result['mode']],['Exported records',len(data)],['Pending records',len(pending)],['Approved repairs',len(decisions)],['Extra column policy',extra_headers],['Notice','Data includes structurally accepted rows and approved mappings. It does not certify factual accuracy.'],*([['Warning',w] for w in result['warnings'] if len(w)<30000])])
        if pending:
            sheet('Review Index',['Source line','Field count','Reason'],([r['line'],len(r['raw']),r['reason']] for r in pending),all_highlight=True)
            sheet('Needs Review',['Source line','Original field','Part','Total parts','Encoding','Original value'],long_rows((r['line'],i,v) for r in pending for i,v in enumerate(r['raw'],1)),all_highlight=True)
        if extras: sheet('Extra Fields',['Source line','Field','Part','Total parts','Encoding','Original value'],long_rows(extras),all_highlight=True)
        if original: sheet('Original Repairs',['Source line','Original field','Part','Total parts','Encoding','Original value'],long_rows(original),all_highlight=True)
        if audit: sheet('Repair Report',['Source line','Action','Details'],audit)
        if suggestions: sheet('Suggested Repairs',['Source line','Field','Part','Total parts','Encoding','Suggested value'],long_rows((line,f'{i}: {h}',v) for line,i,h,v in suggestions),all_highlight=True)
        sheet('Original Headers',['Source line','Original field','Part','Total parts','Encoding','Header value'],long_rows((result.get('header_line',1),i,h) for i,h in enumerate(result['source_headers'],1)))
        sheet('Data Line Map',['Excel record number','Source line'],([i,line] for i,(line,_) in enumerate(data,1)))
        with tempfile.NamedTemporaryFile(dir=output.parent,suffix='.xlsx',delete=False) as f: temp=f.name
        wb.save(temp); os.replace(temp,output)
    finally:
        wb.close()
        if temp and os.path.exists(temp): os.unlink(temp)
    return {'output_file':str(output),'records':len(data),'review_count':len(pending),'repair_count':len(decisions),'extra_count':len(extras),'columns':len(keep)}

def convert_tsv_to_excel(file_path=None,text=None,output_path=None,mode='business',decisions=None,extra_headers='keep'):
    r=validate_tsv(file_path=file_path,text=text,mode=mode)
    if output_path is None:
        if file_path is None: raise ValueError('Choose an output filename.')
        output_path=Path(file_path).with_suffix('.xlsx')
    return export_result(r,output_path,decisions,extra_headers)

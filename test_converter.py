"""Run with python -m unittest -v test_converter. Uses synthetic data only."""
import csv
import io
import tempfile
import unittest
from pathlib import Path
from openpyxl import load_workbook
from schema import STANDARD_COLUMNS
from validator import validate_tsv,resolve_row
from converter import export_result

class ConverterTests(unittest.TestCase):
    def setUp(self): self.temp=tempfile.TemporaryDirectory(); self.path=Path(self.temp.name)/'out.xlsx'
    def tearDown(self): self.temp.cleanup()
    def workbook(self,result,decisions=None,policy='keep'):
        export_result(result,self.path,decisions,policy); w=load_workbook(self.path); self.addCleanup(w.close); return w
    def test_general_text_and_quoted_fields(self):
        r=validate_tsv(text='A\tB\tC\n07036\t"a\tb\nc"\t=1+1\n',mode='general'); self.assertTrue(r['valid']); self.assertEqual(r['rows'],[['07036','a\tb\nc','=1+1']]); w=self.workbook(r); self.assertEqual(w['Data']['A2'].value,'07036'); self.assertEqual(w['Data']['B2'].value,'a\tb\nc'); self.assertEqual(w['Data']['C2'].data_type,'s')
    def test_general_ragged_records_not_guessed(self):
        r=validate_tsv(text='A\tB\nx\ty\nx\ty\tz\na\n',mode='general'); self.assertEqual(len(r['rows']),1); self.assertEqual(len(r['review']),2); self.assertIsNone(r['review'][0]['suggestion']); w=self.workbook(r); self.assertIn('Needs Review',w.sheetnames); self.assertEqual(w['Data'].max_row,2)
    def test_keep_and_discard_extra(self):
        r=validate_tsv(text='A\tB\nx\ty\tz\n',mode='general'); d={2:{'mapping':[0,2],'discard':False}}; w=self.workbook(r,d); self.assertEqual(w['Data']['B2'].value,'z'); self.assertEqual(w['Extra Fields']['F2'].value,'y'); w.close(); d[2]['discard']=True; w=self.workbook(r,d); self.assertNotIn('Extra Fields',w.sheetnames); self.assertNotIn('y',[c.value for row in w['Original Repairs'] for c in row]); self.assertIn('Discarded by explicit user approval',[c.value for row in w['Repair Report'] for c in row])
    def test_duplicate_mapping_rejected(self):
        with self.assertRaises(ValueError): resolve_row({'raw':['x','y']},[0,0],2)
    def test_unknown_header_kept_and_manual_override(self):
        text='Business Name\tCustom Contact\tOther\nExample\t555-123-4567\tNote\n'; r=validate_tsv(text=text); self.assertEqual(len(r['extra_columns']),2); idx=r['source_mapping'][:28]; idx[24]=1; r=validate_tsv(text=text,header_override=(r['source_headers'],idx)); self.assertEqual(r['rows'][0][24],'555-123-4567'); self.assertEqual(len(r['extra_columns']),1); w=self.workbook(r,policy='separate'); self.assertEqual(w['Extra Fields']['F2'].value,'Note'); self.assertEqual(w['Data'].max_column,28)
    def test_duplicate_header_not_lost(self):
        r=validate_tsv(text='Name\tCompany Name\nA\tB\n'); self.assertEqual(r['rows'][0][0],'A'); self.assertEqual(r['rows'][0][-1],'B'); self.assertEqual(len(r['extra_columns']),1)
    def test_blank_insert_or_remove_suggestion(self):
        row=['']*28; row[0]='Example'; row[13]='Linden, NJ'; row[15]='Mon-Fri: 9 AM - 5 PM'; row[18]='123 Main St'; row[20]='Linden'; row[21]='NJ'; row[22]='07036'; row[24]='555-123-4567'; row[27]='2026-11-25'; raw=row[:15]+['']+row[15:]; f=io.StringIO(); writer=csv.writer(f,delimiter='\t');writer.writerow(STANDARD_COLUMNS);writer.writerow(raw); r=validate_tsv(text=f.getvalue()); self.assertEqual(len(r['review']),1); x=r['review'][0];self.assertIsNotNone(x['mapping']); self.assertEqual([v for v in x['suggestion'] if v],[v for v in raw if v]); self.assertEqual(x['suggestion'][15],row[15]); self.assertFalse(r['rows']); w=self.workbook(r,{x['line']:{'mapping':x['mapping'],'discard':False}}); self.assertEqual(w['Data']['W2'].value,'07036')
    def test_bom_and_empty_record(self):
        p=Path(self.temp.name)/'a.tsv'; p.write_bytes('A\tB\n\t\n'.encode('utf-16')); r=validate_tsv(file_path=p,mode='general'); self.assertEqual(r['rows'],[['','']])
    def test_malformed_quote_preserved(self):
        r=validate_tsv(text='A\tB\nx\ty\n"unclosed\tfield\nlast\trow\n',mode='general'); self.assertEqual(len(r['rows']),1); self.assertTrue(r['review'][0]['unparsed']); self.assertIn('last\trow',r['review'][0]['raw'][0]); w=self.workbook(r); self.assertIn('last\trow',w['Needs Review']['F2'].value)
    def test_long_cells_preserved_in_review(self):
        s='X'*40000; r=validate_tsv(text='A\tB\nx\t'+s+'\n',mode='general'); self.assertFalse(r['rows']); w=self.workbook(r); self.assertEqual(''.join(row[5].value for row in list(w['Needs Review'].rows)[1:] if row[1].value=='2'),s)
    def test_split_workbook_rows(self):
        import converter
        orig=converter.MAX_ROWS
        try:
            converter.MAX_ROWS=3; r=validate_tsv(text='A\tB\n1\ta\n2\tb\n3\tc\n',mode='general'); w=self.workbook(r); self.assertEqual(w['Data'].max_row,3); self.assertEqual(w['Data 2']['A2'].value,'3')
        finally: converter.MAX_ROWS=orig

if __name__=='__main__': unittest.main()

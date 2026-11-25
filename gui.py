"""PyQt5 interface for loss-aware TSV conversion."""
from pathlib import Path
from PyQt5.QtCore import Qt, QUrl, QThread, pyqtSignal, QAbstractTableModel, QModelIndex
from PyQt5.QtGui import QDesktopServices, QColor
from PyQt5.QtWidgets import (QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFileDialog, QMessageBox, QTabWidget, QPlainTextEdit, QTableView, QComboBox,
    QDialog, QDialogButtonBox, QSplitter, QAbstractItemView, QProgressBar)
from validator import validate_tsv, resolve_row
from converter import export_result

class Worker(QThread):
    done=pyqtSignal(object)
    failed=pyqtSignal(str)
    def __init__(self, fn): super().__init__(); self.fn=fn
    def run(self):
        try: self.done.emit(self.fn())
        except Exception as e: self.failed.emit(str(e))

class TableModel(QAbstractTableModel):
    def __init__(self, headers=(), rows=(), highlighted=(), all_highlight=False, parent=None):
        super().__init__(parent); self.headers=headers; self.rows=rows; self.highlighted=set(highlighted); self.all_highlight=all_highlight
    def rowCount(self,parent=QModelIndex()): return 0 if parent.isValid() else len(self.rows)
    def columnCount(self,parent=QModelIndex()): return 0 if parent.isValid() else len(self.headers)
    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid(): return None
        i,j=index.row(),index.column(); row=self.rows[i]; value=str(row[j]) if j<len(row) else ''
        if role==Qt.DisplayRole: return value[:500]+('…' if len(value)>500 else '')
        if role==Qt.ToolTipRole: return value[:4000]
        if role==Qt.BackgroundRole and (self.all_highlight or j in self.highlighted or (len(row)>1 and row[1]=='EXTRA')): return QColor('#FFF2CC')
        if role==Qt.ForegroundRole and (self.all_highlight or j in self.highlighted or (len(row)>1 and row[1]=='EXTRA')): return QColor('#713F12')
    def headerData(self,section,orientation,role=Qt.DisplayRole):
        if orientation==Qt.Horizontal:
            if role==Qt.DisplayRole: return str(self.headers[section])
            if role==Qt.ToolTipRole: return str(self.headers[section])
        elif role==Qt.DisplayRole: return section+1

class MappingModel(TableModel):
    def __init__(self, headers, raw, indices, parent=None):
        super().__init__(['Target column','Source field # (0 = blank)','Mapped value'],[],parent=parent)
        self.targets=headers; self.raw=raw; self.indices=list(indices)
    def rowCount(self,parent=QModelIndex()): return 0 if parent.isValid() else len(self.targets)
    def data(self,index,role=Qt.DisplayRole):
        if not index.isValid(): return None
        i,j=index.row(),index.column(); source=self.indices[i]
        value=[self.targets[i],str(source+1 if source is not None else 0),self.raw[source] if source is not None else ''][j]
        if role==Qt.EditRole and j==1: return value
        if role==Qt.DisplayRole: return str(value)[:500]
        if role==Qt.ToolTipRole: return str(value)[:4000]
        if role==Qt.BackgroundRole and j==1: return QColor('#FFF2CC')
        if role==Qt.ForegroundRole and j==1: return QColor('#713F12')
    def flags(self,index):
        flags=super().flags(index)
        return flags|Qt.ItemIsEditable if index.isValid() and index.column()==1 else flags
    def setData(self,index,value,role=Qt.EditRole):
        if role!=Qt.EditRole or index.column()!=1: return False
        try: n=int(value)
        except (TypeError,ValueError): return False
        if not 0<=n<=len(self.raw): return False
        self.indices[index.row()]=n-1 if n else None
        self.dataChanged.emit(self.index(index.row(),1),self.index(index.row(),2)); return True

class MappingDialog(QDialog):
    def __init__(self,item,headers,previous=None,parent=None,header_mode=False):
        super().__init__(parent); self.item=item; self.headers=headers; self.decision=None; self.header_mode=header_mode
        self.setWindowTitle(f"Review source line {item['line']}"); self.resize(1050,650)
        layout=QVBoxLayout(self); message=QLabel(item['reason']); message.setWordWrap(True); message.setTextFormat(Qt.PlainText); layout.addWidget(message)
        instruction=QLabel('Edit the yellow Source field # cells. Use the number from the original fields on the left, or 0 for a missing value. Each source field can be used only once.'); instruction.setWordWrap(True); layout.addWidget(instruction)
        splitter=QSplitter(Qt.Horizontal); self.source=QTableView(); self.target=QTableView()
        raw=item['raw']; idx=previous['mapping'] if previous else item['mapping']
        # Do not suggest positional mapping for an unequal-width generic row without evidence.
        self.model=MappingModel(headers,raw,idx if idx is not None else [None]*len(headers),self)
        self.target.setModel(self.model); self.target.setColumnWidth(0,160); self.target.setColumnWidth(1,160); self.target.horizontalHeader().setStretchLastSection(True)
        self.source.setColumnWidth(0,100); self.source.horizontalHeader().setStretchLastSection(True)
        splitter.addWidget(self.source); splitter.addWidget(self.target); layout.addWidget(splitter,1)
        self.extra=QLabel(); self.extra.setWordWrap(True); layout.addWidget(self.extra)
        self.model.dataChanged.connect(self.refresh); self.refresh()
        buttons=QDialogButtonBox(QDialogButtonBox.Cancel)
        keep=buttons.addButton('Apply header mapping' if header_mode else 'Approve & keep extras separately',QDialogButtonBox.AcceptRole); keep.clicked.connect(lambda:self.finish(False))
        if not header_mode:
            discard=buttons.addButton('Approve & discard extras…',QDialogButtonBox.ActionRole); discard.clicked.connect(lambda:self.finish(True))
        buttons.rejected.connect(self.reject); layout.addWidget(buttons)
    def refresh(self,*_):
        used=set(self.model.indices); rows=[[i+1,'Mapped' if i in used else 'EXTRA',v] for i,v in enumerate(self.item['raw'])]
        old=self.source.model(); self.source.setModel(TableModel(['Field #','Status','Original value'],rows,parent=self.source))
        if old: old.deleteLater()
        self.source.setColumnWidth(0,70); self.source.setColumnWidth(1,90)
        self.extra.setText(f'{sum(i not in used for i in range(len(rows)))} original fields are unassigned. They will be kept separately by default.')
    def finish(self,discard):
        try: d=resolve_row(self.item,self.model.indices,len(self.headers),discard)
        except ValueError as e: QMessageBox.warning(self,'Check mapping',str(e)); return
        if all(i is None for i in self.model.indices): QMessageBox.warning(self,'No mapping','Assign at least one source field, or cancel to keep this record in Needs Review.'); return
        if discard and d['extras']:
            if QMessageBox.question(self,'Discard original fields?',f"Permanently omit {len(d['extras'])} unassigned fields from this exported workbook? Your input file is not modified. Choose No to return to review.",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes: return
        self.decision={'mapping':d['mapping'],'discard':discard}; self.accept()

class DropArea(QLabel):
    file_dropped=pyqtSignal(str)
    def __init__(self):
        super().__init__('Drag & drop a TSV or TXT file here'); self.setObjectName('dropArea'); self.setAlignment(Qt.AlignCenter); self.setAcceptDrops(True); self.setMinimumHeight(65)
    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: event.ignore()
    def dragMoveEvent(self,event):
        if event.mimeData().hasUrls(): event.acceptProposedAction()
        else: event.ignore()
    def dropEvent(self,event):
        urls=event.mimeData().urls()
        if len(urls)==1 and urls[0].isLocalFile(): self.file_dropped.emit(urls[0].toLocalFile()); event.acceptProposedAction()
        else: event.ignore(); QMessageBox.warning(self,'One file at a time','Drop one local file.')

class MainWindow(QWidget):
    def __init__(self):
        super().__init__(); self.input_file=None; self.output_file=None; self.result=None; self.decisions={}; self.worker=None
        self.setWindowTitle('TSV to Excel Converter - v1.1.0'); self.resize(1200,820); self.setMinimumSize(780,650)
        layout=QVBoxLayout(self); heading=QLabel('TSV to Excel Converter'); heading.setObjectName('heading'); heading.setAlignment(Qt.AlignCenter); layout.addWidget(heading)
        mode_row=QHBoxLayout(); mode_row.addWidget(QLabel('Conversion mode:')); self.mode=QComboBox(); self.mode.addItem('Smart Business (28 standard columns + extras)','business'); self.mode.addItem('General TSV (original columns)','general'); mode_row.addWidget(self.mode,1); layout.addLayout(mode_row)
        self.tabs=QTabWidget(); ft=QWidget(); fl=QVBoxLayout(ft); self.drop=DropArea(); self.drop.file_dropped.connect(self.select_file); fl.addWidget(self.drop)
        browse=QPushButton('Browse File'); browse.clicked.connect(self.browse); fl.addWidget(browse); self.file_label=QLabel('No file selected'); self.file_label.setTextFormat(Qt.PlainText); fl.addWidget(self.file_label)
        pt=QWidget(); pl=QVBoxLayout(pt); self.text=QPlainTextEdit(); self.text.setPlaceholderText('Paste tab-separated data, including headers.'); self.text.setLineWrapMode(QPlainTextEdit.NoWrap); pl.addWidget(self.text)
        self.tabs.addTab(ft,'Import File'); self.tabs.addTab(pt,'Paste TSV Data'); self.tabs.setMaximumHeight(215); layout.addWidget(self.tabs)
        buttons=QHBoxLayout(); self.preview=QPushButton('Validate & Preview'); self.preview.clicked.connect(self.analyze); buttons.addWidget(self.preview); self.convert=QPushButton('Convert to Excel'); self.convert.clicked.connect(self.export); buttons.addWidget(self.convert); layout.addLayout(buttons)
                # Clear All button
        self.clear_button = QPushButton("Clear All")
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.setToolTip("Clear all data and start again")
        self.clear_button.clicked.connect(self.clear_all)

        self.clear_button.setStyleSheet("""
            QPushButton {
                background-color: #FEE2E2;
                color: #B91C1C;
                border: 1px solid #FECACA;
                border-radius: 6px;
                padding: 12px 20px;
                font-weight: bold;
            }

            QPushButton:hover {
                background-color: #DC2626;
                color: white;
            }

            QPushButton:pressed {
                background-color: #991B1B;
                color: white;
            }

            QPushButton:disabled {
                background-color: #E2E8F0;
                color: #94A3B8;
            }
        """)

        buttons.addWidget(self.clear_button)
        self.views=QTabWidget(); self.clean=self.table(); self.review=self.table(); self.suggest=self.table(); self.views.addTab(self.clean,'Accepted data'); self.views.addTab(self.review,'Review queue'); self.views.addTab(self.suggest,'Suggested / approved mapping'); layout.addWidget(self.views,1)
        review_buttons=QHBoxLayout(); self.edit=QPushButton('Review / map selected row'); self.edit.clicked.connect(self.review_selected); self.review.doubleClicked.connect(lambda _:self.review_selected()); review_buttons.addWidget(self.edit)
        self.map_headers=QPushButton('Map input headers…'); self.map_headers.clicked.connect(self.remap_headers); review_buttons.addWidget(self.map_headers)
        self.bulk=QPushButton('Approve all suggestions…'); self.bulk.clicked.connect(self.approve_all); review_buttons.addWidget(self.bulk); self.undo=QPushButton('Undo selected approval'); self.undo.clicked.connect(self.undo_selected); review_buttons.addWidget(self.undo); layout.addLayout(review_buttons)
        self.progress=QProgressBar(); self.progress.setRange(0,0); self.progress.hide(); layout.addWidget(self.progress)
        self.status=QLabel('Import or paste data, then validate. Yellow fields need review.'); self.status.setObjectName('status'); self.status.setWordWrap(True); self.status.setTextFormat(Qt.PlainText); layout.addWidget(self.status)
        self.folder=QPushButton('Open Output Folder'); self.folder.setEnabled(False); self.folder.clicked.connect(self.open_folder); layout.addWidget(self.folder)
        self.mode.currentIndexChanged.connect(self.invalidate); self.tabs.currentChanged.connect(self.invalidate); self.text.textChanged.connect(self.invalidate); self.invalidate()
    def table(self):
        t=QTableView(); t.setAlternatingRowColors(True); t.setSelectionBehavior(QAbstractItemView.SelectRows); t.setSelectionMode(QAbstractItemView.SingleSelection); t.setEditTriggers(QAbstractItemView.NoEditTriggers); t.horizontalHeader().setDefaultSectionSize(145); return t
    def model(self,view,headers,rows,highlighted=(),all_highlight=False):
        old=view.model(); view.setModel(TableModel(headers,rows,highlighted,all_highlight,view));
        if old: old.deleteLater()
    def clear_all(self):

        if self.worker is not None:
            return

        self.input_file = None
        self.output_file = None

        self.text.clear()
        self.file_label.setText("No file selected")
        self.file_label.setToolTip("")

                # Restore the original drag-and-drop area
        self.drop.setText(
            "Drag & drop a TSV or TXT file here"
        )
        self.drop.setStyleSheet("")
        self.drop.setToolTip("")

        self.tabs.setCurrentIndex(0)
        self.views.setCurrentIndex(0)

        self.invalidate()

        self.folder.setEnabled(False)

        self.status.setText(
            "Ready! Import a new file or paste TSV data."
        )    
    def invalidate(self,*_):
        self.result=None; self.decisions={}
        for v in (self.clean,self.review,self.suggest): self.model(v,[],[])
        self.status.setText('Input changed. Click Validate & Preview.'); self.controls()
    def controls(self):
        busy=self.worker is not None; ready=self.result is not None and not busy; count=bool(ready and self.result['review'])
        self.mode.setEnabled(not busy); self.tabs.setEnabled(not busy); self.preview.setEnabled(not busy); self.convert.setEnabled(ready); self.edit.setEnabled(count); self.bulk.setEnabled(bool(count and any(x['mapping'] is not None and x['line'] not in self.decisions for x in self.result['review']))); self.undo.setEnabled(bool(ready and self.decisions)); self.progress.setVisible(busy); self.map_headers.setEnabled(bool(ready and self.result['mode']=='business'))
    def browse(self):
        path,_=QFileDialog.getOpenFileName(self,'Select TSV file','','Tab-separated (*.tsv *.txt);;All files (*)')
        if path: self.select_file(path)
    
    def select_file(self, path):

        p = Path(path)

        if not p.is_file():
            QMessageBox.warning(
                self, "Invalid file", "Choose a local file."
            )
            return

        self.input_file = p
        self.tabs.setCurrentIndex(0)
        self.file_label.setText(str(p))

        # Show successful file selection
        self.drop.setTextFormat(Qt.PlainText)
        self.drop.setText(
            f"✓ File Selected Successfully\n{p.name}"
        )

        self.drop.setStyleSheet("""
            QLabel {
                background-color: #F0FDF4;
                border: 2px dashed #16A34A;
                border-radius: 10px;
                color: #15803D;
                font-size: 17px;
                font-weight: bold;
            }
        """)

        self.drop.setToolTip(str(p))

        self.invalidate()
        self.status.setText(
            "File selected. Click Validate & Preview."
        )
    def start(self,fn,callback):
        self.worker=Worker(fn); self.worker.done.connect(callback); self.worker.failed.connect(self.error); self.worker.finished.connect(self.finished); self.controls(); self.worker.start()
    def finished(self):
        w=self.worker; self.worker=None; w.deleteLater(); self.controls()
    def analyze(self,checked=False,header_override=None):
        self.invalidate(); mode=self.mode.currentData()
        if self.tabs.currentIndex()==0:
            if self.input_file is None: self.error('Choose a file first.'); return
            p=self.input_file; fn=lambda:validate_tsv(file_path=p,mode=mode,header_override=header_override)
        else:
            text=self.text.toPlainText(); fn=lambda:validate_tsv(text=text,mode=mode,header_override=header_override)
        self.status.setText('Validating all records…'); self.start(fn,self.analyzed)
    def analyzed(self,r):
        if not r['valid']: self.error('\n'.join(r['errors'])); return
        self.result=r; self.refresh(); self.views.setCurrentIndex(1 if r['review'] else 0)
    def refresh(self):
        r=self.result; h=r['headers']; self.model(self.clean,h,r['rows'],r['extra_columns']); queue=[]; proposals=[]
        for x in r['review']:
            d=self.decisions.get(x['line']); state='Approved' if d else 'Pending'; queue.append([x['line'],state,len(x['raw']),x['reason'],x['raw'][0] if x['raw'] else ''])
            if d: proposals.append([x['line'],state]+resolve_row(x,d['mapping'],len(h),d['discard'])['row'])
            elif x['suggestion'] is not None: proposals.append([x['line'],state]+x['suggestion'])
        self.model(self.review,['Source line','Status','Field count','Reason','First field'],queue,all_highlight=True); self.review.setColumnWidth(3,370)
        self.model(self.suggest,['Source line','Status']+h,proposals,all_highlight=True)
        self.status.setText(f"Accepted: {len(r['accepted'])} | Pending: {len(queue)-len(self.decisions)} | Approved: {len(self.decisions)} | Columns: {len(h)} | Extra headers: {len(r['extra_columns'])}. "+' '.join(r['warnings'])[:700]); self.controls()
    def remap_headers(self):
        from schema import STANDARD_COLUMNS
        r=self.result
        if self.decisions and QMessageBox.question(self,'Revalidate?','Changing headers resets row approvals. Continue?',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes: return
        item={'line':r['header_line'],'raw':r['source_headers'],'mapping':r['source_mapping'][:len(STANDARD_COLUMNS)],'reason':'Map source headers to the standard business columns. Unassigned headers will remain highlighted extra columns.'}
        d=MappingDialog(item,STANDARD_COLUMNS,parent=self,header_mode=True)
        if d.exec_()==QDialog.Accepted: self.analyze(header_override=(r['source_headers'],d.decision['mapping']))
    def selected(self):
        i=self.review.currentIndex().row()
        if i<0 or not self.result: QMessageBox.information(self,'Select a row','Select a record in the Review queue tab.'); return None
        return self.result['review'][i]
    def review_selected(self):
        x=self.selected()
        if not x: return
        if x.get('unparsed'): QMessageBox.information(self,'Raw record preserved','This record cannot be mapped losslessly. It will remain in Needs Review.'); return
        d=MappingDialog(x,self.result['headers'],self.decisions.get(x['line']),self)
        if d.exec_()==QDialog.Accepted: self.decisions[x['line']]=d.decision; self.refresh()
    def undo_selected(self):
        x=self.selected()
        if x: self.decisions.pop(x['line'],None); self.refresh()
    def approve_all(self):
        items=[x for x in self.result['review'] if x['mapping'] is not None and x['line'] not in self.decisions and not x.get('unparsed')]
        if not items: return
        if QMessageBox.question(self,'Approve all inferred mappings?',f"Apply {len(items)} suggestions, including ambiguous ones? Review the Suggested mapping tab first. All unassigned fields will be kept in Extra Fields. No fields are discarded.",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes: return
        for x in items: self.decisions[x['line']]={'mapping':x['mapping'],'discard':False}
        self.refresh()
    def export(self):
        if not self.result: return
        r=self.result; policy='keep'
        if r['extra_columns']:
            msg=QMessageBox(self); msg.setWindowTitle('Extra input columns'); msg.setText(f"{len(r['extra_columns'])} unrecognized or duplicate header columns found. How should they be exported?")
            keep=msg.addButton('Keep highlighted in Data',QMessageBox.AcceptRole); separate=msg.addButton('Keep separately',QMessageBox.ActionRole); discard=msg.addButton('Discard extra columns…',QMessageBox.DestructiveRole); cancel=msg.addButton(QMessageBox.Cancel); msg.setDefaultButton(keep); msg.exec_(); b=msg.clickedButton()
            if b==cancel or b is None: return
            if b==separate: policy='separate'
            if b==discard:
                if QMessageBox.question(self,'Confirm discard','Omit all values in extra header columns from Data and approved repairs? Unresolved original rows will still be preserved. Your source file is unchanged.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes: return
                policy='discard'
        pending=len(r['review'])-len(self.decisions)
        if pending and QMessageBox.question(self,'Unresolved records',f'{pending} records remain pending. Export accepted/approved rows and keep pending raw records in Needs Review?',QMessageBox.Yes|QMessageBox.No,QMessageBox.Yes)!=QMessageBox.Yes: return
        default=str(self.input_file.with_suffix('.xlsx')) if self.tabs.currentIndex()==0 and self.input_file else str(Path.home()/'converted_data.xlsx')
        filename,_=QFileDialog.getSaveFileName(self,'Save Excel workbook',default,'Excel (*.xlsx)',options=QFileDialog.DontConfirmOverwrite)
        if not filename: return
        p=Path(filename)
        if p.suffix.lower()!='.xlsx': p=p.with_suffix('.xlsx')
        if self.input_file and p.resolve()==self.input_file.resolve(): self.error('Choose a different output file.'); return
        if p.exists() and QMessageBox.question(self,'Overwrite workbook?',f'Replace {p.name}?',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes: return
        decisions=dict(self.decisions); self.status.setText('Writing Excel workbook…'); self.start(lambda:export_result(r,p,decisions,policy),self.exported)
    def exported(self,out):
        self.output_file=Path(out['output_file']); self.folder.setEnabled(True); detail=f"Exported: {out['records']} | Pending: {out['review_count']} | Approved: {out['repair_count']} | Separate fields: {out['extra_count']}\n{self.output_file}"
        self.status.setText(detail); msg=QMessageBox(self); msg.setWindowTitle('Workbook saved'); msg.setTextFormat(Qt.PlainText); msg.setText(detail); open_button=msg.addButton('Open Folder',QMessageBox.ActionRole); msg.addButton(QMessageBox.Ok); msg.exec_()
        if msg.clickedButton()==open_button: self.open_folder()
    def open_folder(self):
        if self.output_file and not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.output_file.parent))): self.error('Cannot open the folder.')
    def error(self,text):
        self.status.setText('Error: '+text); msg=QMessageBox(self); msg.setWindowTitle('Application Error'); msg.setIcon(QMessageBox.Critical); msg.setTextFormat(Qt.PlainText); msg.setText(text); msg.exec_()
    def closeEvent(self,event):
        if self.worker is not None: QMessageBox.information(self,'Operation running','Wait until the current operation finishes before closing.'); event.ignore()
        else: event.accept()

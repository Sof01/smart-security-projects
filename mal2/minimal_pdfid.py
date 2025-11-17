# minimal_pdfid.py
# Nur die Teile, die für PDFiD() + PDFiD2JSON() nötig sind.

import sys, io, json, math, operator, traceback
import xml.dom.minidom

__version__ = '0.2.7-min'

def C2BIP3(string):
    return bytes([ord(x) for x in string]) if sys.version_info[0] > 2 else string

class cBinaryFile:
    """Unterstützt Dateipfad (str) oder Bytes (bytes)."""
    def __init__(self, file_or_bytes):
        if isinstance(file_or_bytes, bytes):
            self.infile = io.BytesIO(file_or_bytes)
        else:
            self.infile = open(file_or_bytes, 'rb')
        self.ungetted = []

    def byte(self):
        if self.ungetted:
            return self.ungetted.pop()
        b = self.infile.read(1)
        if not b:
            self.infile.close()
            return None
        return b[0]

    def bytes(self, size):
        if size <= len(self.ungetted):
            res = self.ungetted[:size]
            del self.ungetted[:size]
            return res
        rest = self.infile.read(size - len(self.ungetted)) or b''
        res = self.ungetted + list(rest)
        self.ungetted = []
        return res

    def unget(self, byte):
        self.ungetted.append(byte)

    def ungets(self, bytes_list):
        bytes_list.reverse()
        self.ungetted.extend(bytes_list)

class cPDFDate:
    def __init__(self): self.state = 0
    def parse(self, char):
        if char == 'D': self.state = 1; return None
        if self.state == 1:
            if char == ':': self.state = 2; self.digits1 = ''; return None
            self.state = 0; return None
        if self.state == 2:
            if len(self.digits1) < 14 and '0' <= char <= '9':
                self.digits1 += char; return None
            if char in '+-Z': self.state = 3; self.digits2 = ''; self.TZ = char; return None
            if char == '"' or char < '0' or char > '9':
                self.state = 0; self.date = 'D:' + self.digits1; return self.date
            self.state = 0; return None
        if self.state == 3:
            if len(self.digits2) < 2 and '0' <= char <= '9':
                self.digits2 += char; return None
            if len(self.digits2) == 2 and char == "'":
                self.digits2 += char; return None
            if len(self.digits2) < 5 and '0' <= char <= '9':
                self.digits2 += char
                if len(self.digits2) == 5:
                    self.state = 0; self.date = 'D:' + self.digits1 + self.TZ + self.digits2; return self.date
                return None
            self.state = 0; return None

def fEntropy(countByte, countTotal):
    x = float(countByte) / countTotal
    return -x * math.log(x, 2) if x > 0 else 0.0

class cEntropy:
    def __init__(self):
        self.allBucket = [0]*256
        self.streamBucket = [0]*256
    def add(self, byte, insideStream):
        self.allBucket[byte] += 1
        if insideStream: self.streamBucket[byte] += 1
    def removeInsideStream(self, byte):
        if self.streamBucket[byte] > 0: self.streamBucket[byte] -= 1
    def calc(self):
        nonStreamBucket = list(map(operator.sub, self.allBucket, self.streamBucket))
        allCount = sum(self.allBucket)
        streamCount = sum(self.streamBucket)
        nonCount = sum(nonStreamBucket)
        ent_all = sum(fEntropy(x, allCount) for x in self.allBucket) if allCount else 0.0
        ent_stream = (sum(fEntropy(x, streamCount) for x in self.streamBucket) if streamCount else None)
        ent_non = sum(fEntropy(x, nonCount) for x in nonStreamBucket) if nonCount else 0.0
        return (allCount, ent_all, streamCount, ent_stream, nonCount, ent_non)

class cPDFEOF:
    def __init__(self):
        self.token = ''; self.cntEOFs = 0; self.cntCharsAfterLastEOF = 0
    def parse(self, char):
        if self.cntEOFs > 0: self.cntCharsAfterLastEOF += 1
        t = self.token
        if t == '' and char == '%': self.token = '%'; return
        if t == '%' and char == '%': self.token = '%%'; return
        if t == '%%' and char == 'E': self.token = '%%E'; return
        if t == '%%E' and char == 'O': self.token = '%%EO'; return
        if t == '%%EO' and char == 'F': self.token = '%%EOF'; return
        if t == '%%EOF' and char in ('\n', '\r', ' ', '\t'):
            self.cntEOFs += 1; self.cntCharsAfterLastEOF = 0
            self.token = '' if char == '\n' else '%%EOF' + char; return
        if t == '%%EOF\r':
            if char == '\n': self.cntCharsAfterLastEOF = 0
            self.token = ''
        else:
            self.token = ''

def FindPDFHeaderRelaxed(oBinaryFile):
    bytes_head = oBinaryFile.bytes(1024)
    s = ''.join(chr(b) for b in bytes_head)
    idx = s.find('%PDF')
    if idx == -1:
        oBinaryFile.ungets(bytes_head)
        return ([], None)
    for endHeader in range(idx + 4, idx + 14):
        if bytes_head[endHeader] in (10, 13): break
    oBinaryFile.ungets(bytes_head[endHeader:])
    return (bytes_head[0:endHeader], s[idx:endHeader])

def Hexcode2String(c): return '#%02x' % c if isinstance(c, int) else c
def SwapCase(c): return ord(chr(c).swapcase()) if isinstance(c, int) else c.swapcase()
def HexcodeName2String(name): return ''.join(map(Hexcode2String, name))
def SwapName(wordExact): return map(SwapCase, wordExact)

def UpdateWords(word, wordExact, slash, words, hexcode, allNames, lastName, insideStream, oEntropy, fOut=None):
    if word != '':
        full = slash + word
        if full in words:
            words[full][0] += 1
            if hexcode: words[full][1] += 1
        elif slash == '/' and allNames:
            words[full] = [1, 1 if hexcode else 0]
        if slash == '/': lastName = full
        if slash == '':
            if word == 'stream': insideStream = True
            if word == 'endstream':
                if insideStream and oEntropy is not None:
                    for ch in 'endstream': oEntropy.removeInsideStream(ord(ch))
                insideStream = False
        if fOut is not None: fOut.write(C2BIP3(HexcodeName2String(wordExact)))
    return ('', [], False, lastName, insideStream)

class cCVE_2009_3459:
    def __init__(self): self.count = 0
    def Check(self, lastName, word):
        if lastName == '/Colors' and word.isdigit() and int(word) > 2**24:
            self.count += 1

def ParseINIFile():
    # Minimal: ignoriert pdfid.ini und liefert keine Extra-Keywords
    return []

def PDFiD(file_or_bytes, allNames=False, extraData=False, force=False):
    """
    Liefert ein xml.dom.minidom.Document mit den Zählwerten/Meta-Daten.
    file_or_bytes: Pfad (str) oder Bytes (bytes)
    """
    word = ''; wordExact = []; hexcode = False; lastName = ''; insideStream = False
    keywords = ['obj','endobj','stream','endstream','xref','trailer','startxref',
                '/Page','/Encrypt','/ObjStm','/JS','/JavaScript','/AA','/OpenAction',
                '/AcroForm','/JBIG2Decode','/RichMedia','/Launch','/EmbeddedFile','/XFA']
    for ek in ParseINIFile():
        if ek not in keywords: keywords.append(ek)
    words = {k:[0,0] for k in keywords}
    dates = []

    xmlDoc = xml.dom.minidom.getDOMImplementation().createDocument(None, 'PDFiD', None)
    def _set(name, value): a = xmlDoc.createAttribute(name); a.nodeValue = value; xmlDoc.documentElement.setAttributeNode(a); return a
    _set('Version', __version__)
    _set('Filename', '<bytes>' if isinstance(file_or_bytes, bytes) else str(file_or_bytes))
    attErr = _set('ErrorOccured', 'False'); attMsg = _set('ErrorMessage','')

    oPDFDate = (cPDFDate() if extraData else None)
    oEntropy = (cEntropy() if extraData else None)
    oPDFEOF  = (cPDFEOF()  if extraData else None)
    oCVE = cCVE_2009_3459()

    try:
        attIsPDF = xmlDoc.createAttribute('IsPDF'); xmlDoc.documentElement.setAttributeNode(attIsPDF)
        oBinaryFile = cBinaryFile(file_or_bytes)
        (bytesHeader, pdfHeader) = FindPDFHeaderRelaxed(oBinaryFile)
        if oEntropy is not None:
            for b in bytesHeader: oEntropy.add(b, insideStream)
        if pdfHeader is None and not force:
            attIsPDF.nodeValue = 'False'
            return xmlDoc
        attIsPDF.nodeValue = 'True' if pdfHeader is not None else 'False'
        _set('Header', repr((pdfHeader or '')[:10]).strip("'"))

        byte = oBinaryFile.byte()
        slash = ''
        while byte is not None:
            ch = chr(byte); chU = ch.upper()
            if ('A' <= chU <= 'Z') or ('0' <= chU <= '9'):
                word += ch; wordExact.append(ch)
            elif slash == '/' and ch == '#':
                d1 = oBinaryFile.byte(); d2 = oBinaryFile.byte()
                if d1 is not None and d2 is not None:
                    c1, c2 = chr(d1), chr(d2)
                    if (c1.isdigit() or 'A' <= c1.upper() <= 'F') and (c2.isdigit() or 'A' <= c2.upper() <= 'F'):
                        word += chr(int(c1 + c2, 16)); wordExact.append(int(c1 + c2, 16)); hexcode = True
                        if oEntropy is not None: oEntropy.add(d1, insideStream); oEntropy.add(d2, insideStream)
                        if oPDFEOF is not None: oPDFEOF.parse(c1); oPDFEOF.parse(c2)
                    else:
                        if d2 is not None: oBinaryFile.unget(d2)
                        if d1 is not None: oBinaryFile.unget(d1)
                        (word, wordExact, hexcode, lastName, insideStream) = UpdateWords(word, wordExact, slash, words, hexcode, allNames, lastName, insideStream, oEntropy)
                else:
                    if d2 is not None: oBinaryFile.unget(d2)
                    if d1 is not None: oBinaryFile.unget(d1)
                    (word, wordExact, hexcode, lastName, insideStream) = UpdateWords(word, wordExact, slash, words, hexcode, allNames, lastName, insideStream, oEntropy)
            else:
                oCVE.Check(lastName, word)
                (word, wordExact, hexcode, lastName, insideStream) = UpdateWords(word, wordExact, slash, words, hexcode, allNames, lastName, insideStream, oEntropy)
                slash = '/' if ch == '/' else ''
            if oPDFDate is not None and oPDFDate.parse(ch) is not None:
                dates.append([oPDFDate.date, lastName])
            if oEntropy is not None: oEntropy.add(byte, insideStream)
            if oPDFEOF is not None: oPDFEOF.parse(ch)
            byte = oBinaryFile.byte()

        (word, wordExact, hexcode, lastName, insideStream) = UpdateWords(word, wordExact, slash, words, hexcode, allNames, lastName, insideStream, oEntropy)
        if byte is None and oPDFEOF is not None and oPDFEOF.token == '%%EOF':
            oPDFEOF.cntEOFs += 1; oPDFEOF.cntCharsAfterLastEOF = 0; oPDFEOF.token = ''

    except SystemExit:
        raise
    except Exception:
        attErr.nodeValue = 'True'
        attMsg.nodeValue = traceback.format_exc()

    # Entropie/EOF-Attribute
    for name in ('TotalEntropy','TotalCount','StreamEntropy','StreamCount','NonStreamEntropy','NonStreamCount','CountEOF','CountCharsAfterLastEOF'):
        _set(name, '')
    if oEntropy is not None:
        cAll,eAll,cStr,eStr,cNon,eNon = oEntropy.calc()
        _set('TotalEntropy', '%f' % eAll); _set('TotalCount', '%d' % cAll)
        _set('StreamEntropy', 'N/A' if eStr is None else '%f' % eStr); _set('StreamCount', '%d' % cStr)
        _set('NonStreamEntropy', '%f' % eNon); _set('NonStreamCount', '%d' % cNon)
    if oPDFEOF is not None:
        _set('CountEOF','%d' % oPDFEOF.cntEOFs)
        _set('CountCharsAfterLastEOF', '%d' % oPDFEOF.cntCharsAfterLastEOF if oPDFEOF.cntEOFs>0 else '')

    # Keywords
    eleKeywords = xmlDoc.createElement('Keywords'); xmlDoc.documentElement.appendChild(eleKeywords)
    for k in keywords:
        ek = xmlDoc.createElement('Keyword'); eleKeywords.appendChild(ek)
        a = xmlDoc.createAttribute('Name'); a.nodeValue = k; ek.setAttributeNode(a)
        a = xmlDoc.createAttribute('Count'); a.nodeValue = str(words[k][0]); ek.setAttributeNode(a)
        a = xmlDoc.createAttribute('HexcodeCount'); a.nodeValue = str(words[k][1]); ek.setAttributeNode(a)
    # /Colors > 2^24
    ek = xmlDoc.createElement('Keyword'); eleKeywords.appendChild(ek)
    a = xmlDoc.createAttribute('Name'); a.nodeValue = '/Colors > 2^24'; ek.setAttributeNode(a)
    a = xmlDoc.createAttribute('Count'); a.nodeValue = str(oCVE.count); ek.setAttributeNode(a)
    a = xmlDoc.createAttribute('HexcodeCount'); a.nodeValue = '0'; ek.setAttributeNode(a)

    # Dates
    eleDates = xmlDoc.createElement('Dates'); xmlDoc.documentElement.appendChild(eleDates)
    dates.sort(key=lambda x: x[0])
    for value,name in dates:
        d = xmlDoc.createElement('Date'); eleDates.appendChild(d)
        a = xmlDoc.createAttribute('Value'); a.nodeValue = value; d.setAttributeNode(a)
        a = xmlDoc.createAttribute('Name');  a.nodeValue = name;  d.setAttributeNode(a)

    return xmlDoc

def PDFiD2JSON(xmlDoc, force=False):
    data = {
        'errorOccured': xmlDoc.documentElement.getAttribute('ErrorOccured'),
        'errorMessage': xmlDoc.documentElement.getAttribute('ErrorMessage'),
        'filename':     xmlDoc.documentElement.getAttribute('Filename'),
        'header':       xmlDoc.documentElement.getAttribute('Header'),
        'isPdf':        xmlDoc.documentElement.getAttribute('IsPDF'),
        'version':      xmlDoc.documentElement.getAttribute('Version'),
        'countEof':     xmlDoc.documentElement.getAttribute('CountEOF'),
        'countChatAfterLastEof': xmlDoc.documentElement.getAttribute('CountCharsAfterLastEOF'),
        'totalEntropy': xmlDoc.documentElement.getAttribute('TotalEntropy'),
        'streamEntropy':xmlDoc.documentElement.getAttribute('StreamEntropy'),
        'nonStreamEntropy': xmlDoc.documentElement.getAttribute('NonStreamEntropy'),
        'keywords': {'keyword': []},
        'dates': {'date': []},
    }
    for node in xmlDoc.documentElement.getElementsByTagName('Keywords')[0].childNodes:
        data['keywords']['keyword'].append({
            'name': node.getAttribute('Name'),
            'count': int(node.getAttribute('Count') or 0),
            'hexcodecount': int(node.getAttribute('HexcodeCount') or 0),
        })
    for node in xmlDoc.documentElement.getElementsByTagName('Dates')[0].childNodes:
        data['dates']['date'].append({'name': node.getAttribute('Name'), 'value': node.getAttribute('Value')})
    return json.dumps([{'pdfid': data}])

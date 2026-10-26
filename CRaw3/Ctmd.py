
from struct import Struct
from collections import namedtuple, OrderedDict
from CRaw3.TiffIfd import TiffIfd
from binascii import hexlify

class Ctmd:
  S_CTMD_INDEX_HEADER = Struct('>LLL')
  S_CTMD_INDEX_ENTRY = Struct('>HHL')
  NT_CTMD_INDEX_ENTRY = namedtuple('ctmd_index_entry', 'type size')

  def __init__(self, data, length, base, name): #parse the index, common to all ctmd in mdat if more than one (rolls)
    self.index_list = []
    self.data = data
    
    if len(data) < Ctmd.S_CTMD_INDEX_HEADER.size:
      raise ValueError('Truncated CTMD index header')
    _, _, nb = Ctmd.S_CTMD_INDEX_HEADER.unpack_from( data, 0)
    if nb > (len(data) - Ctmd.S_CTMD_INDEX_HEADER.size) // Ctmd.S_CTMD_INDEX_ENTRY.size:
      raise ValueError('CTMD index entries exceed the index buffer')
    for i in range(nb):
      _, type, size = Ctmd.S_CTMD_INDEX_ENTRY.unpack_from( data, Ctmd.S_CTMD_INDEX_HEADER.size + i*Ctmd.S_CTMD_INDEX_ENTRY.size)
      entry = Ctmd.NT_CTMD_INDEX_ENTRY( type, size )
      self.index_list.append( entry )

  S_CTMD_RECORD_HEADER = Struct('<LHBBHH')  
  NT_CTMD_RECORD = namedtuple('ctmd_record', 'size type offset content')
  CTMD_TIFF_TYPES = [ 7, 8, 9 ]
  S_CTMD_TIFF_HEADER = Struct('<LL')  #record size, tag id

  CTMD_TYPE_TIMESTAMP = 1
  S_CTMD_TIMESTAMP = Struct('<HHBBBBBB')
  NT_CTMD_TIMESTAMP = namedtuple('ctmd_timestamp', 'y mo d h m s ms')
  CTMD_TYPE_FOCAL = 4
  S_CTMD_FOCAL = Struct('<HH')
  NT_CTMD_FOCAL = namedtuple('ctmd_focal', 'num denum')
  CTMD_TYPE_EXPOSURE = 5
  S_CTMD_EXPOSURE = Struct('<HHHHL')
  NT_CTMD_EXPOSURE = namedtuple('ctmd_exposure', 'f_num f_denum expo_num expo_denum iso')

  def parse(self, data ):
    self.ctmd_list = OrderedDict()
    if len(self.offsets) != len(self.sizes):
      raise ValueError('CTMD picture offsets and sizes have different counts')
    pic_num = 0
    for file_offset, ctmd_size in zip( self.offsets, self.sizes ): #for all pictures in roll
      if file_offset < 0 or ctmd_size < 0 or file_offset > len(data) or ctmd_size > len(data) - file_offset:
        raise ValueError('CTMD picture range exceeds the file buffer')
      ctmd_data = data[ file_offset: file_offset+ctmd_size ]  
      ctmd_offset = 0
      ctmd_records = dict()
      for type, size in self.index_list: #contains type and size
        if size < Ctmd.S_CTMD_RECORD_HEADER.size or size > len(ctmd_data) - ctmd_offset:
          raise ValueError('CTMD record size is outside its picture buffer')
        ctmd_record = ctmd_data[ ctmd_offset: ctmd_offset+size ]
        record_size, record_type, _, _, _, _ = Ctmd.S_CTMD_RECORD_HEADER.unpack_from( ctmd_record, 0)
        if record_size!=size or record_type!=type:
          raise ValueError('CTMD record type or size does not match its index')
        if record_type in Ctmd.CTMD_TIFF_TYPES:
          record_offset = Ctmd.S_CTMD_RECORD_HEADER.size #inside the record
          ctmd_tiff = dict()
          while record_offset < record_size:
            remaining = record_size - record_offset
            if remaining < Ctmd.S_CTMD_TIFF_HEADER.size:
              raise ValueError('Truncated CTMD TIFF payload header')
            payload_size, payload_tag = Ctmd.S_CTMD_TIFF_HEADER.unpack_from( ctmd_record, record_offset )
            if payload_size < Ctmd.S_CTMD_TIFF_HEADER.size or payload_size > remaining:
              raise ValueError('CTMD TIFF payload size is outside its record')
            payload_start = record_offset + Ctmd.S_CTMD_TIFF_HEADER.size
            payload_end = record_offset + payload_size
            tiff = TiffIfd( ctmd_record[payload_start:payload_end], payload_end-payload_start, file_offset+ctmd_offset+payload_start, b'CTMD%d_0x%x'%(record_type, payload_tag), False)
            ctmd_tiff[ payload_tag ] =  (file_offset+ctmd_offset+record_offset, payload_size, payload_tag, (record_offset+Ctmd.S_CTMD_TIFF_HEADER.size, tiff) )  
            record_offset += payload_size
          ctmd_records[type] = Ctmd.NT_CTMD_RECORD(size, type, file_offset+ctmd_offset, ctmd_tiff)  #store context and TIFF entries		
        else:
          scalar = {Ctmd.CTMD_TYPE_TIMESTAMP: Ctmd.S_CTMD_TIMESTAMP,
                    Ctmd.CTMD_TYPE_EXPOSURE: Ctmd.S_CTMD_EXPOSURE,
                    Ctmd.CTMD_TYPE_FOCAL: Ctmd.S_CTMD_FOCAL}.get(record_type)
          if scalar is not None and record_size - Ctmd.S_CTMD_RECORD_HEADER.size < scalar.size:
            raise ValueError('Truncated CTMD scalar record')
          if record_type == Ctmd.CTMD_TYPE_TIMESTAMP:
            _, y, mo, d, h, m, s, ms = Ctmd.S_CTMD_TIMESTAMP.unpack_from( ctmd_record, Ctmd.S_CTMD_RECORD_HEADER.size )
            ctmd_records[type] = Ctmd.NT_CTMD_RECORD( size, type, file_offset+ctmd_offset, Ctmd.NT_CTMD_TIMESTAMP( y, mo, d, h, m, s, ms ) )
          elif record_type == Ctmd.CTMD_TYPE_EXPOSURE:
            f_num, f_denum, expo_num, expo_denum, iso = Ctmd.S_CTMD_EXPOSURE.unpack_from( ctmd_record, Ctmd.S_CTMD_RECORD_HEADER.size )
            ctmd_records[type] = Ctmd.NT_CTMD_RECORD( size, type, file_offset+ctmd_offset, Ctmd.NT_CTMD_EXPOSURE ( f_num, f_denum, expo_num, expo_denum, iso ) )   
          elif record_type == Ctmd.CTMD_TYPE_FOCAL:
            num, denum = Ctmd.S_CTMD_FOCAL.unpack_from( ctmd_record, Ctmd.S_CTMD_RECORD_HEADER.size )
            ctmd_records[type] = Ctmd.NT_CTMD_RECORD( size, type, file_offset+ctmd_offset, Ctmd.NT_CTMD_FOCAL ( num, denum ) )
          else:        
            ctmd_records[type] = Ctmd.NT_CTMD_RECORD( size, type, file_offset+ctmd_offset, None) #do not store content, but type, size and pointer for later processing
        ctmd_offset += size
      self.ctmd_list[ pic_num ] =  ctmd_records  
      pic_num += 1      
    return self.ctmd_list	

  def display(self):
    for pic_num, ctmd in self.ctmd_list.items():
      #generic way to list CTMD entries
      for ctmd_record in ctmd.values():
        print('offset=0x%x, size=%d, type=%d: ' % (ctmd_record.offset, ctmd_record.size, ctmd_record.type ), end='' ) 
        if ctmd_record.type in Ctmd.CTMD_TIFF_TYPES: #TIFF
          print('list')
          for subdir_tag, tiff_subdir in ctmd_record.content.items():
            offset, payload_size, payload_tag, entries = tiff_subdir
            print('  0x%04x: size=%d tag=0x%x offset_base=%x' % (offset, payload_size, payload_tag, entries[0]) )
            entries[1].display( 1 )  
        else: #not TIFF
          if ctmd_record.type in [ Ctmd.CTMD_TYPE_TIMESTAMP, Ctmd.CTMD_TYPE_EXPOSURE, Ctmd.CTMD_TYPE_FOCAL ]:
            print( ctmd_record.content )
          else:
            ctmd_data = self.data[ ctmd_record.offset: ctmd_record.offset+ctmd_record.size] #we do not know how to parse it
            print('%s' % hexlify(ctmd_data) )

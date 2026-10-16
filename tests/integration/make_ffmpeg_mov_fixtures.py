#!/usr/bin/env python3
from pathlib import Path
import argparse
import struct,json,hashlib,subprocess
parser=argparse.ArgumentParser(description="Generate bounded synthetic MOV/PSSH fixtures and independent expected side-data bytes.")
parser.add_argument("output",type=Path)
args=parser.parse_args()
p=args.output
p.mkdir(parents=True,exist_ok=True)
for name,maps in [("base.mov",["-map","0:a"]),("base-two.mov",["-map","0:a","-map","0:a"])]:
    subprocess.run(["ffmpeg","-nostdin","-v","error","-y","-f","lavfi","-i","sine=frequency=1000:sample_rate=8000","-t","0.5",*maps,"-c:a","pcm_s16le","-movflags","empty_moov+frag_keyframe+default_base_moof","-frag_duration","100000",str(p/name)],check=True)
u32=lambda n:struct.pack('>I',n)
def box(t,b):return u32(len(b)+8)+t+b
def boxes(b):
 o=0
 while o<len(b):
  n=int.from_bytes(b[o:o+4],'big');assert n>=8 and o+n<=len(b)
  yield b[o+4:o+8],b[o+8:o+n];o+=n
 assert o==len(b)
def record(i):
 version=i%2;sid=bytes([i%251])*16;keys=[bytes([(i+j+1)%251])*16 for j in range(i%3)] if version else []
 data=bytes([i%239])*(i%11)
 payload=bytes([version,0,0,0])+sid+(u32(len(keys))+b''.join(keys) if version else b'')+u32(len(data))+data
 serialized=u32(16)+u32(len(keys))+u32(16)+u32(len(data))+sid+b''.join(keys)+data
 return box(b'pssh',payload),serialized
manifest=[]
def create(name,n,streams=1,fragments=False):
 original=(p/('base-two.mov' if streams==2 else 'base.mov')).read_bytes();expected=[[] for _ in range(streams)];out=b'';track=0;frag=0
 for t,b in boxes(original):
  if t==b'moov':
   children=b''
   for ct,cb in boxes(b):
    children+=box(ct,cb)
    if ct==b'trak':
     for i in range(n):
      atom,wire=record(i+track*101);children+=atom;expected[track].append(wire)
     track+=1
   out+=box(t,children)
  elif t==b'mfra':continue # offsets changed; no absolute fragment index in generated fixtures
  else:
   if t==b'moof':
    if fragments and frag:
     for i in range(3):
      atom,wire=record(n+frag*3+i);out+=atom;expected[-1].append(wire)
    frag+=1
   out+=box(t,b)
 (p/(name+'.mov')).write_bytes(out)
 for i,records in enumerate(expected):(p/f'{name}.{i}.bin').write_bytes(u32(len(records))+b''.join(records) if records else b'')
 manifest.append({'name':name,'records':sum(map(len,expected)),'streams':streams,'fragments':fragments,'sha256':hashlib.sha256(out).hexdigest()})
for n in [0,1,7,2048,4096,32768]:create(f'continuous-{n}',n)
create('two-streams',7,2)
create('fragments',17,1,True)
(p/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

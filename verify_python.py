import pathlib, subprocess, time, csv, sys
root=pathlib.Path('stage1'); results=[]
for path in sorted(root.glob('case_*.txt')):
 data=path.read_text().splitlines(); n=int(data[0]); m=int(data[1]); rows=data[2].split(); costs=[tuple(map(int,x.split())) for x in data[3:6]]; target=int(data[6]); limit=int(data[7]) if len(data)>7 else 0
 start=time.perf_counter()
 try:
  proc=subprocess.run([sys.executable,'stage1.py',str(path),'python_output.txt'],capture_output=True,timeout=30)
  elapsed=(time.perf_counter()-start)*1000
  if proc.returncode: raise ValueError(proc.stderr.decode(errors='replace'))
  lines=pathlib.Path('python_output.txt').read_text().splitlines(); gates=[line.split() for line in lines[:-1]]; outs=list(map(int,lines[-1].split())); area=0; delays=[0]*(n+1)
  for t in gates:
   assert int(t[0])==len(delays); op=t[1]; idx={'AND2':0,'OR2':1,'NOT':2}[op]; args=list(map(int,t[2:])); assert len(args)==(1 if op=='NOT' else 2) and all(a<len(delays) for a in args); area+=costs[idx][0]; delays.append(max(delays[a] for a in args)+costs[idx][1])
  assert len(outs)==m and all(x<len(delays) for x in outs)
  # Simulate all rows in blocks of 1024 using Python integers as bit vectors.
  for startrow in range(0,len(rows),1024):
   block=rows[startrow:startrow+1024]; mask=(1<<len(block))-1; vals=[0]+[sum(((startrow+k)>>(n-1-i)&1)<<k for k in range(len(block))) for i in range(n)]
   for t in gates:
    a=vals[int(t[2])]; op=t[1]; vals.append((a^mask) if op=='NOT' else (a & vals[int(t[3])] if op=='AND2' else a | vals[int(t[3])]))
   for j,o in enumerate(outs):
    expected=sum((row[j]=='1')<<k for k,row in enumerate(block)); assert vals[o]==expected
  status='correct' if not limit or elapsed<=limit else 'time limit exceeded'
  results.append([path.name,status,area,max(delays[o] for o in outs),round(elapsed),target,limit]); print(path.name,status,flush=True)
 except Exception as e:
  results.append([path.name,str(e)[:100],'','','',target,limit]); print(path.name,'error',str(e)[:100],flush=True)
 with open('python_results.csv','w',newline='') as f:
  w=csv.writer(f); w.writerow(['case','local_status','area','delay','runtime_ms','target_delay','runtime_limit_ms']); w.writerows(results)

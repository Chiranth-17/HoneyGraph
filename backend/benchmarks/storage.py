"""Regular versus MongoDB time-series storage and range-query benchmark."""
from __future__ import annotations
import time
from datetime import datetime,timedelta,timezone
from benchmarks.common import client,csv_write
def timed(col,q,repeats=5):
 vals=[]
 for _ in range(repeats):
  t=time.perf_counter();list(col.find(q));vals.append((time.perf_counter()-t)*1000)
 return sum(vals)/len(vals)
def run(count=200_000):
 c=client();db=c.benchmark_honeygraph;db.drop_collection('telemetry_regular');db.drop_collection('telemetry_ts');db.create_collection('telemetry_ts',timeseries={'timeField':'ts','metaField':'deviceId','granularity':'minutes'});r=db.telemetry_regular;t=db.telemetry_ts;base=datetime(2026,10,14,tzinfo=timezone.utc)
 for off in range(0,count,10000):
  docs=[{'ts':base+timedelta(seconds=i//500),'deviceId':f'bench-{i%500:04d}','bytesOut':1000+i%200,'bytesIn':500+i%100} for i in range(off,min(off+10000,count))];r.insert_many(docs,ordered=False);t.insert_many(docs,ordered=False)
 r.create_index([('deviceId',1),('ts',1)]);q={'deviceId':'bench-0042','ts':{'$gte':base,'$lt':base+timedelta(minutes=10)}};rows=[]
 for kind,col in [('regular',r),('time_series',t)]:
  s=db.command('collStats',col.name);rows.append({'collection':kind,'documents':count,'storage_bytes':s.get('storageSize',0),'total_index_bytes':s.get('totalIndexSize',0),'range_query_mean_ms':round(timed(col,q),3)})
 csv_write('storage.csv',rows);print(rows);c.close();return rows
if __name__=='__main__':run()

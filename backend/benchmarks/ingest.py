"""Seeded million-document bulk ingestion benchmark."""
from __future__ import annotations
import argparse, hashlib, json, random, time
from datetime import datetime, timedelta, timezone
from pymongo.write_concern import WriteConcern
from benchmarks.common import SEED, client, csv_write

def run(count=1_000_000,batch_size=10_000):
    c=client(); db=c.benchmark_honeygraph; rows=[]
    for chained,name in [(False,'events_plain'),(True,'events_hash')]:
        db.drop_collection(name); col=db[name].with_options(write_concern=WriteConcern(w=1)); rng=random.Random(SEED); heads={}
        started=time.perf_counter(); inserted=0; base=datetime(2026,10,14,tzinfo=timezone.utc)
        for offset in range(0,count,batch_size):
            docs=[]
            for i in range(offset,min(offset+batch_size,count)):
                device=f'bench-{i%500:04d}'; doc={'ts':base+timedelta(milliseconds=i),'deviceId':device,'srcIp':f'198.51.100.{1+i%250}','eventType':['login_failed','telemetry','mqtt_publish'][i%3],'protocol':['ssh','http','mqtt'][i%3],'value':rng.randrange(1_000_000)}
                if chained:
                    prev=heads.get(device,'0'*64); material=json.dumps(doc,sort_keys=True,default=str,separators=(',',':')).encode(); digest=hashlib.sha256(prev.encode()+material).hexdigest(); doc.update(prevHash=prev,hash=digest); heads[device]=digest
                docs.append(doc)
            col.insert_many(docs,ordered=False); inserted+=len(docs)
        seconds=time.perf_counter()-started; rows.append({'mode':'hash_chain' if chained else 'plain','events':inserted,'seconds':round(seconds,3),'events_per_second':round(inserted/seconds,1),'target_5000_eps':inserted/seconds>=5000})
    csv_write('ingest.csv',rows); print(rows); c.close(); return rows
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--count',type=int,default=1_000_000);p.add_argument('--batch-size',type=int,default=10_000);a=p.parse_args();run(a.count,a.batch_size)

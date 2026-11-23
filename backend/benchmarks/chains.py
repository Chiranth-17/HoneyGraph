"""Known four-hop graph reconstruction check."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from bson import ObjectId
from benchmarks.common import client,csv_write
from workers.chain_builder import ChainBuilder
def run():
 c=client();db=c.honeygraph;tag=ObjectId();base=datetime.now(timezone.utc);ids=[]
 try:
  for i in range(4):
   d={'ts':base+timedelta(milliseconds=i),'ruleId':'BENCH-CHAIN','deviceId':f'bench-chain-{tag}-{i}','actor':f'10.250.0.{i+1}','targetIp':f'10.250.0.{i+2}','stage':'lateral-movement','severity':8,'eventIds':[ObjectId()],'eventInsertedAt':base,'alertCreatedAt':base,'dedupeKey':f'{tag}-{i}'};ids.append(db.alerts.insert_one(d).inserted_id)
  chain=ChainBuilder(c,db.name).reconstruct(ids[-1]);hops=[x['hop'] for x in chain if x['ruleId']=='BENCH-CHAIN'];row={'expected_hops':4,'recovered_hops':len(hops),'ordered':hops==[0,1,2,3],'full_recovery':len(hops)==4 and hops==[0,1,2,3]};csv_write('chains.csv',[row]);print(row);return row
 finally: db.alerts.delete_many({'ruleId':'BENCH-CHAIN'});c.close()
if __name__=='__main__':run()

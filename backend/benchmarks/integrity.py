"""Exact-position integrity benchmark on an isolated chain."""
from __future__ import annotations
from datetime import datetime,timedelta,timezone
from app.hashchain import GENESIS_HASH,compute_hash
from benchmarks.common import client,csv_write
from workers.integrity_checker import check_device
def run():
 c=client();db=c.honeygraph;dev='benchmark-integrity-104729';db.events.delete_many({'deviceId':dev});prev=GENESIS_HASH;docs=[];base=datetime.now(timezone.utc)
 for i in range(1,7):
  d={'ts':base+timedelta(milliseconds=i),'deviceId':dev,'protocol':'ssh','eventType':'login_failed','srcIp':'192.0.2.199','geo':{'type':'Point','coordinates':[77.59,12.97]},'payload':{'user':'bench','attempts':i},'prevHash':prev,'chainSeq':i};d['hash']=compute_hash(prev,d);prev=d['hash'];docs.append(d)
 db.events.insert_many(docs);db.events.update_one({'deviceId':dev,'chainSeq':3},{'$set':{'eventType':'tampered_benchmark'}});broken=check_device(db,dev);row={'mutation':'modify','expected_position':3,'reported_position':broken.position,'reason':broken.reason,'pass':broken.position==3 and broken.reason=='modified'};csv_write('integrity.csv',[row]);print(row);db.events.delete_many({'deviceId':dev});c.close();return row
if __name__=='__main__':run()

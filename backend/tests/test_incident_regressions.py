"""Regressions for incident creation and correlation used by the dashboard."""
import asyncio
import os
import runpy
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

from app.api_models import ScenarioRequest, StatusRequest
from app.routers import incidents, scenarios
from workers.chain_builder import ChainBuilder
from workers.detector import Detector

load_dotenv()


def test_mirai_materializes_detected_incidents(monkeypatch):
    called=[]
    incident_id=str(ObjectId())

    async def ingest(events):return [{"id":str(ObjectId())} for _ in events]
    def materialize(ids,name):called.append((ids,name));return [incident_id]

    # The helper is implemented alongside the general scenario-to-incident flow.
    monkeypatch.setattr(scenarios,'_build_scenario_incidents',materialize,raising=False)
    app=SimpleNamespace(state=SimpleNamespace(
        scenario_jobs={'mirai':{}},db=SimpleNamespace(devices=SimpleNamespace(find=lambda *a:[])),
        ingestion=SimpleNamespace(ingest=ingest)))
    asyncio.run(scenarios.execute(app,'mirai',ScenarioRequest(name='mirai_bruteforce',seed=707)))
    assert called and called[0][1]=='mirai_bruteforce'
    assert app.state.scenario_jobs['mirai']['incidentIds']==[incident_id]


@pytest.fixture
def isolated_alerts():
    with MongoClient(os.environ['MONGODB_URI']) as client:
        db=client[os.getenv('MONGO_DATABASE','honeygraph')]
        marker=uuid4().hex
        ids=[]
        devices=[]
        def insert(actor,target,ts):
            device='incident-regression-'+uuid4().hex;devices.append(device)
            doc={'ts':ts,'ruleId':marker,'deviceId':device,'actor':actor,'targetIp':target,
                 'stage':'initial-access','severity':8,'eventIds':[ObjectId()],
                 'eventInsertedAt':ts,'alertCreatedAt':ts,'dedupeKey':uuid4().hex}
            identifier=db.alerts.insert_one(doc).inserted_id;ids.append(identifier);return identifier
        yield client,db,marker,insert
        # Delete only these explicitly created fixture records.
        db.incidents.delete_many({'chain.alertId':{'$in':ids}})
        db.alerts.delete_many({'_id':{'$in':ids}})
        db.risk_scores.delete_many({'deviceId':{'$in':devices}})


def test_same_source_alerts_form_one_incident(isolated_alerts):
    client,db,actor,insert=isolated_alerts
    now=datetime.now(timezone.utc)-timedelta(seconds=10)
    first=insert(actor,actor+'-target',now)
    second=insert(actor,actor+'-target',now+timedelta(seconds=1))
    incident_id=ChainBuilder(client,db.name).build(second)
    row=db.incidents.find_one({'_id':incident_id})
    assert {a['alertId'] for a in row['chain']}=={first,second}


def test_expanding_open_chain_keeps_incident_and_history(isolated_alerts):
    client,db,actor,insert=isolated_alerts
    now=datetime.now(timezone.utc)-timedelta(seconds=10)
    first=insert(actor,actor+'-one',now)
    builder=ChainBuilder(client,db.name)
    initial=builder.build(first)
    second=insert(actor+'-one',actor+'-two',now+timedelta(seconds=1))
    expanded=builder.build(second)
    assert expanded==initial
    row=db.incidents.find_one({'_id':initial})
    assert len(row['chain'])==2 and len(row['statusHistory'])==1
    assert db.incidents.count_documents({'chain.alertId':first})==1


def test_status_change_uses_compare_and_swap():
    identifier=ObjectId()
    class Collection:
        def __init__(self):self.state='open';self.history=[]
        def find_one(self,query):return {'_id':identifier,'status':'open'}
        def update_one(self,query,update):
            if query.get('status',self.state)!=self.state:return SimpleNamespace(matched_count=0)
            self.state=update['$set']['status'];self.history.append(update['$push']['statusHistory'])
            return SimpleNamespace(matched_count=1)
    collection=Collection()
    request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=SimpleNamespace(incidents=collection))))
    incidents.transition(str(identifier),StatusRequest(status='triaged'),request,{'username':'analyst'})
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        incidents.transition(str(identifier),StatusRequest(status='triaged'),request,{'username':'analyst'})
    assert error.value.status_code==409
    assert len(collection.history)==1


def test_lateral_rule_cites_the_current_event(isolated_alerts):
    client,db,actor,_=isolated_alerts
    module=runpy.run_path(str(Path(__file__).resolve().parents[2]/'mongo/seed_rules.py'))
    rule=next(item for item in module['rules']() if item['ruleId']=='R-LATERAL-06')
    now=datetime.now(timezone.utc)
    events=[{'ts':now-timedelta(seconds=2-index),'deviceId':actor,'protocol':'ssh',
             'eventType':'lateral_login','srcIp':actor,'geo':{'type':'Point','coordinates':[77.59,12.97]},
             'payload':{'user':'service','attempts':1},'prevHash':'0'*64,'hash':'1'*64}
            for index in range(2)]
    ids=db.events.insert_many(events).inserted_ids
    try:
        result=Detector(client,db.name)._evaluate(rule,events[-1])
        assert [row['_id'] for row in result]==[ids[-1]]
    finally:
        db.events.delete_many({'_id':{'$in':ids}})


def test_cycle_keeps_root_and_unique_alerts(isolated_alerts):
    client,db,actor,insert=isolated_alerts
    now=datetime.now(timezone.utc)-timedelta(seconds=10)
    ids=[insert(actor,actor+'-one',now),
         insert(actor+'-one',actor+'-two',now+timedelta(seconds=1)),
         insert(actor+'-two',actor+'-one',now+timedelta(seconds=2))]
    row=db.incidents.find_one({'_id':ChainBuilder(client,db.name).build(ids[-1])})
    assert row['chain'][0]['alertId']==ids[0] and row['chain'][0]['hop']==0
    assert len(row['chain'])==3


def test_rebuild_does_not_reopen_closed_incident(isolated_alerts):
    client,db,actor,insert=isolated_alerts
    identifier=insert(actor,actor+'-one',datetime.now(timezone.utc))
    builder=ChainBuilder(client,db.name);incident=builder.build(identifier)
    db.incidents.update_one({'_id':incident},{'$set':{'status':'closed'}})
    before=db.incidents.find_one({'_id':incident})
    assert builder.build(identifier)==incident
    assert db.incidents.find_one({'_id':incident})==before

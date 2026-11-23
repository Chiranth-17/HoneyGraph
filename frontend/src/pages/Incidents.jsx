import {useCallback,useEffect,useRef,useState} from 'react';
import {Route,Routes,useNavigate,useParams} from 'react-router-dom';
import {DataSet} from 'vis-data';
import {Network} from 'vis-network';
import {GitBranch,RefreshCw,Siren} from 'lucide-react';
import {api} from '../api';
import {useAuth} from '../auth';
import {Empty,ErrorBox,Loading,Severity,fmt} from '../components';
import {Header} from './Alerts';

// Ignore stale responses after navigation; failed requests must end loading.
function useIncidentResource(path,token,poll=0){
  const [data,setData]=useState(null);
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(true);
  const generation=useRef(0);
  const load=useCallback(async()=>{
    const current=++generation.current;
    setLoading(true);
    try{
      const next=await api(path,{token});
      if(current===generation.current){
        setData(previous=>next._id&&previous?._id===next._id&&previous.updatedAt===next.updatedAt?previous:next);
        setError('');
      }
    }catch(e){if(current===generation.current)setError(e.message)}
    finally{if(current===generation.current)setLoading(false)}
  },[path,token]);
  useEffect(()=>{
    setData(null);load();
    const timer=poll?setInterval(load,poll):null;
    window.addEventListener('focus',load);
    return()=>{generation.current++;clearInterval(timer);window.removeEventListener('focus',load)};
  },[load,poll]);
  function replace(value){generation.current++;setData(value);setLoading(false);setError('')}
  return {data,error,loading,load,replace};
}

export default function Incidents(){
  return <Routes><Route index element={<IncidentList/>}/><Route path=":id" element={<IncidentDetail/>}/></Routes>;
}

function IncidentList(){
  const {session}=useAuth();
  const nav=useNavigate();
  const [pageNumber,setPageNumber]=useState(1);
  const {data,error,loading,load}=useIncidentResource(`/incidents?pageNumber=${pageNumber}`,session.token,3000);
  return <>
    <Header title="Incidents" subtitle="Correlated alerts and ordered attack chains · refreshes automatically" icon={Siren}
      right={<button className="btn-secondary flex items-center gap-2" onClick={load} disabled={loading}><RefreshCw className="h-4"/>Refresh</button>}/>
    <ErrorBox error={error}/>
    {loading&&!data?<Loading/>:data?.items.length?<div className="grid gap-4 xl:grid-cols-2">{data.items.map(i=><button onClick={()=>nav(i._id)} key={i._id} className="card p-5 text-left transition hover:border-honey/60">
      <div className="flex justify-between gap-3"><span className="badge bg-cyan/10 text-cyan">{i.status||'open'}</span><span className="text-xs text-slate-500">{fmt(i.updatedAt)}</span></div>
      <h3 className="mt-4 font-bold">Chain {i._id.slice(-8)}</h3>
      <p className="mt-2 text-sm text-slate-400">{i.chain?.length||0} linked alerts · {new Set(i.chain?.map(x=>x.deviceId)).size||0} devices</p>
      {i.chain?.[0]&&<p className="mt-2 break-all font-mono text-xs text-cyan">Source {i.chain[0].actor}</p>}
      <div className="mt-4 flex gap-2">{i.chain?.slice(0,4).map(x=><Severity key={x.alertId} value={x.severity}/>)}</div>
    </button>)}</div>:!error&&<Empty label="No correlated incidents yet."/>}
    {data&&<div className="mt-5 flex items-center justify-between gap-3 text-sm text-slate-400"><button className="btn-ghost" disabled={pageNumber===1||loading} onClick={()=>setPageNumber(p=>p-1)}>Previous</button><span>Page {pageNumber} · {data.total} incidents</span><button className="btn-ghost" disabled={pageNumber*50>=data.total||loading} onClick={()=>setPageNumber(p=>p+1)}>Next</button></div>}
  </>;
}

function IncidentDetail(){
  const {id}=useParams();
  const {session}=useAuth();
  const nav=useNavigate();
  const {data:item,error,loading,load,replace}=useIncidentResource(`/incidents/${id}`,session.token,5000);
  const [writeError,setWriteError]=useState('');
  const [graphError,setGraphError]=useState('');
  const [updating,setUpdating]=useState(false);
  const ref=useRef();
  useEffect(()=>{
    if(!item?.chain?.length||!ref.current)return;
    setGraphError('');
    const byIp=new Map();const edges=[];
    item.chain.forEach((a,index)=>{
      for(const [ip,label,level] of [[a.actor,a.actor,a.hop],[a.targetIp,`${a.deviceId||a.targetIp}\n${a.targetIp}`,a.hop+1]]){
        const existing=byIp.get(ip);
        if(existing){existing.level=Math.min(existing.level,level);if(ip===a.targetIp)existing.label=label}
        else byIp.set(ip,{id:ip,label,level,shape:'dot',size:18,color:index===0&&ip===a.actor?'#f6b73c':'#38d7ff',font:{color:'#dce7f7'}});
      }
      edges.push({id:a.alertId,from:a.actor,to:a.targetIp,label:`${a.hop} · ${a.stage}\n${a.ruleId}`,arrows:'to',color:'#64748b',smooth:{enabled:true,type:'curvedCW',roundness:.12+(index%4)*.08},font:{color:'#94a3b8',size:11,strokeWidth:0}});
    });
    try{
      const network=new Network(ref.current,{nodes:new DataSet([...byIp.values()]),edges:new DataSet(edges)},{physics:false,layout:{hierarchical:{enabled:true,direction:'LR',sortMethod:'directed',nodeSpacing:180,levelSeparation:220}},interaction:{hover:true}});
      return()=>network.destroy();
    }catch(e){setGraphError(`Could not draw the graph: ${e.message}`)}
  },[item?.chain]);
  async function transition(status){
    if(updating)return;
    setUpdating(true);setWriteError('');
    try{replace(await api(`/incidents/${id}/status`,{token:session.token,method:'PATCH',body:{status}}))}
    catch(e){setWriteError(e.message);load()}
    finally{setUpdating(false)}
  }
  const next=item?.status==='open'?'triaged':item?.status==='triaged'?'closed':null;
  return <>
    <Header title={`Incident ${id.slice(-8)}`} subtitle="Ordered attack-chain reconstruction" icon={GitBranch} right={<div className="flex flex-wrap gap-2"><button className="btn-secondary" onClick={()=>nav('/incidents')}>All incidents</button><button className="btn-secondary" onClick={load} disabled={loading}>Refresh</button>{next&&<button className="btn-primary" disabled={updating} onClick={()=>transition(next)}>{updating?'Updating…':`Mark ${next}`}</button>}</div>}/>
    <ErrorBox error={error||writeError||graphError}/>
    {loading&&!item?<Loading/>:item&&<div className="grid gap-5 xl:grid-cols-[2fr_1fr]">
      <section className="card p-4">{item.chain?.length?<div ref={ref} className="h-[500px] rounded-xl bg-slate-950/60"/>:<Empty label="This incident has no chain evidence."/>}</section>
      <section className="card p-5"><p className="label">Status history</p><div className="mt-5 space-y-5">{item.statusHistory?.map((entry,index)=><div className="relative border-l-2 border-line pl-5" key={index}><span className="absolute -left-[6px] top-1 h-2.5 w-2.5 rounded-full bg-honey"/><b className="capitalize">{entry.status}</b><p className="text-xs text-slate-500">{fmt(entry.ts)} {entry.by&&`· ${entry.by}`}</p></div>)}</div>
      <p className="label mt-8">Chain evidence</p><div className="mt-3 space-y-2">{item.chain?.map(a=><div className="rounded-xl bg-slate-950/60 p-3" key={a.alertId}><div className="flex justify-between"><b>Hop {a.hop}</b><Severity value={a.severity}/></div><p className="mt-1 break-all text-xs text-slate-400">{a.actor} → {a.targetIp}</p><p className="text-xs text-cyan">{a.ruleId} · {a.stage}</p></div>)}</div></section>
    </div>}
  </>;
}

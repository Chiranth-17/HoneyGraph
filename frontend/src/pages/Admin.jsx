import {useEffect,useState} from 'react';
import {Link} from 'react-router-dom';
import {Play,Square,UserPlus,Users} from 'lucide-react';
import {api} from '../api';
import {useAuth} from '../auth';
import {Empty,ErrorBox,Loading} from '../components';
import {Header} from './Alerts';

const scenarios=['mirai_bruteforce','recon','credential_stuffing','mqtt_abuse','lateral_movement','exfil_burst','log_tamper'];
const stoppable=['queued','running','detecting'];

function Evidence({data,job,onBuild,busy}){
  if(!data)return <Loading label="Reading stored evidence..."/>;
  return <section className="card mt-5 p-5" aria-label="Scenario evidence">
    <p className="label">Selected run: {job?.name}</p>
    <h3 className="mt-2 text-xl font-bold">Events → Alerts → Incidents</h3>
    <p className="mt-2 text-sm text-slate-400">The simulator sends activity records. MongoDB change streams trigger detection automatically. Correlation joins related alerts into an incident.</p>
    <div className="mt-5 grid gap-4 lg:grid-cols-3">
      <div className="rounded-xl border border-line p-4">
        <h4 className="font-bold text-cyan">1. Stored events · {data.counts.events}</h4>
        <p className="my-2 text-xs text-slate-400">Raw observations, validated and hash chained in events.</p>
        <div className="max-h-80 space-y-2 overflow-auto">{data.events.length?data.events.map(e=><details key={e._id} className="rounded bg-slate-950/60 p-2 text-xs"><summary className="cursor-pointer"><b>{e.eventType}</b><span className="block break-all text-slate-400">{e._id}</span></summary><pre className="mt-2 whitespace-pre-wrap break-all">{JSON.stringify(e,null,2)}</pre></details>):<Empty label="Waiting for events."/>}</div>
      </div>
      <div className="rounded-xl border border-line p-4">
        <h4 className="font-bold text-amber-300">2. Detected alerts · {data.counts.alerts}</h4>
        <p className="my-2 text-xs text-slate-400">Stored rule pipelines match events. Expand to see eventIds linking the evidence.</p>
        <div className="max-h-80 space-y-2 overflow-auto">{data.alerts.length?data.alerts.map(a=><details key={a._id} className="rounded bg-slate-950/60 p-2 text-xs"><summary className="cursor-pointer"><b>{a.ruleId} · {a.stage}</b><span className="block break-all text-slate-400">{a._id}</span></summary><pre className="mt-2 whitespace-pre-wrap break-all">{JSON.stringify(a,null,2)}</pre></details>):<Empty label="No matching alerts yet."/>}</div>
      </div>
      <div className="rounded-xl border border-line p-4">
        <h4 className="font-bold text-emerald-300">3. Correlated incidents · {data.counts.incidents}</h4>
        <p className="my-2 text-xs text-slate-400">MongoDB $graphLookup connects alerts. One transaction stores the incident, alert links and risk updates.</p>
        {data.incidents.map(i=><Link key={i._id} to={`/incidents/${i._id}`} className="my-3 block break-all text-sm text-cyan underline">Open incident {i._id}</Link>)}
        {!data.counts.incidents&&<p className="my-3 text-sm text-slate-400">No incident has been built for this run.</p>}
        {job?.status==='awaiting_correlation'&&<button onClick={onBuild} disabled={busy} className="btn-primary mt-2">3. Build incident</button>}
        {job?.status==='correlating'&&<p className="text-sm text-amber-300">Building the chain...</p>}
        {job?.deferCorrelation&&<p className="mt-3 text-xs text-slate-500">Presentation mode pauses here until you request correlation.</p>}
      </div>
    </div>
    <p className="mt-3 text-xs text-slate-500">Counts come from MongoDB for this run only. Up to 200 records per stage are displayed.</p>
    <details className="mt-4 rounded-xl border border-line p-3"><summary className="cursor-pointer text-sm text-cyan">Show the same evidence in MongoDB Compass</summary><p className="mt-2 text-xs text-slate-400">Open honeygraph, select each collection and paste its filter into the Documents filter bar.</p>{Object.entries(data.compassFilters).map(([name,filter])=><div className="mt-3" key={name}><b className="text-xs">{name}</b><pre className="max-h-28 overflow-auto whitespace-pre-wrap break-all rounded bg-slate-950/60 p-2 text-xs">{filter}</pre></div>)}</details>
  </section>;
}

export default function Admin(){
  const {session}=useAuth();
  const [users,setUsers]=useState(null),[jobs,setJobs]=useState([]);
  const [scenario,setScenario]=useState('mirai_bruteforce'),[guided,setGuided]=useState(false);
  const [selected,setSelected]=useState(null),[evidence,setEvidence]=useState(null);
  const [launching,setLaunching]=useState(false),[building,setBuilding]=useState(false);
  const [form,setForm]=useState({username:'',password:'',role:'analyst'}),[error,setError]=useState('');
  const token=session.token;
  async function load(){try{const [u,j]=await Promise.all([api('/users',{token}),api('/scenarios',{token})]);setUsers(u);setJobs(j)}catch(e){setError(e.message)}}
  useEffect(()=>{load();const timer=setInterval(async()=>{try{setJobs(await api('/scenarios',{token}))}catch(e){setError(e.message)}},2000);return()=>clearInterval(timer)},[token]);
  useEffect(()=>{
    if(!selected)return;
    let cancelled=false;
    setEvidence(null);
    async function refresh(){try{const data=await api(`/scenarios/${selected}/evidence`,{token});if(!cancelled)setEvidence(data)}catch(e){if(!cancelled)setError(e.message)}}
    refresh();const timer=setInterval(refresh,2000);
    return()=>{cancelled=true;clearInterval(timer)};
  },[selected,token]);
  async function launch(){setLaunching(true);setError('');try{
    const job=await api('/scenarios/launch',{token,method:'POST',body:{name:scenario,seed:Date.now()%2147483647,deferCorrelation:guided}});
    setJobs(old=>[...old.filter(j=>j.id!==job.id),job]);setSelected(job.id);await load();
  }catch(e){setError(e.message)}finally{setLaunching(false)}}
  async function build(){setBuilding(true);setError('');try{
    const job=await api(`/scenarios/${selected}/correlate`,{token,method:'POST'});
    setJobs(old=>old.map(j=>j.id===job.id?job:j));
    setEvidence(await api(`/scenarios/${selected}/evidence`,{token}));
  }catch(e){setError(e.message)}finally{setBuilding(false)}}
  async function stop(id){try{await api(`/scenarios/${id}/stop`,{token,method:'POST'});await load()}catch(e){setError(e.message)}}
  async function create(e){e.preventDefault();try{await api('/users',{token,method:'POST',body:form});setForm({username:'',password:'',role:'analyst'});await load()}catch(e){setError(e.message)}}
  async function active(u){try{await api(`/users/${u.username}`,{token,method:'PATCH',body:{active:!u.active}});await load()}catch(e){setError(e.message)}}
  const selectedJob=jobs.find(j=>j.id===selected);
  return <>
    <Header title="Scenarios & Users" subtitle="Controlled simulation and workspace administration" icon={Users}/>
    <ErrorBox error={error}/>
    <div className="grid gap-5 lg:grid-cols-2">
      <section className="card p-5">
        <p className="label">Simulation control</p><h3 className="mt-2 text-xl font-bold">Launch defensive scenario</h3>
        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm"><input type="checkbox" checked={guided} onChange={e=>setGuided(e.target.checked)}/>Step-by-step demo (pause before incidents)</label>
        <p className="mt-2 text-xs text-slate-400">{guided?'Generate events, inspect automatically detected alerts, then build the incident yourself.':'Automatic mode generates events, detects alerts and builds incidents in one flow.'}</p>
        <div className="mt-5 flex flex-wrap gap-3"><select aria-label="Scenario" className="field min-w-0 flex-1" value={scenario} onChange={e=>setScenario(e.target.value)}>{scenarios.map(s=><option key={s}>{s}</option>)}</select><button disabled={launching} className="btn-primary flex items-center gap-2" onClick={launch}><Play className="h-4"/>{launching?'Launching...':guided?'1. Generate events':'Launch'}</button></div>
        <div className="mt-6 max-h-96 space-y-3 overflow-auto">{jobs.length?[...jobs].reverse().map(j=><div className="rounded-xl bg-slate-950/60 p-4" key={j.id}><div className="flex items-center justify-between gap-3"><div><b>{j.name}</b><p className="text-xs text-slate-500">seed {j.seed} · {j.status.replaceAll('_',' ')}</p></div>{stoppable.includes(j.status)&&<button aria-label={`Stop ${j.name}`} className="btn-ghost" onClick={()=>stop(j.id)}><Square className="h-3"/></button>}</div>{j.error&&<p className="mt-1 text-xs text-red-300">{j.error}</p>}{j.message&&<p className="mt-1 text-xs text-amber-300">{j.message}</p>}<button className="mt-3 text-xs text-cyan underline" onClick={()=>setSelected(j.id)}>Inspect process</button>{j.incidentId&&<Link className="ml-4 text-xs text-cyan underline" to={`/incidents/${j.incidentId}`}>Open incident</Link>}</div>):<Empty label="No scenario jobs in this backend session."/>}</div>
      </section>
      <section className="card p-5">
        <p className="label">Account management</p>
        <form className="mt-4 grid gap-3 sm:grid-cols-2" onSubmit={create}><input className="field" placeholder="Username" value={form.username} onChange={e=>setForm({...form,username:e.target.value})}/><input className="field" type="password" placeholder="Password (8+ chars)" value={form.password} onChange={e=>setForm({...form,password:e.target.value})}/><select className="field" value={form.role} onChange={e=>setForm({...form,role:e.target.value})}><option>analyst</option><option>admin</option></select><button className="btn-primary flex items-center justify-center gap-2"><UserPlus className="h-4"/>Create user</button></form>
        <div className="mt-6 max-h-64 space-y-2 overflow-auto">{users?.map(u=><div className="flex items-center justify-between rounded-xl border border-line p-3" key={u.username}><div><b>{u.username}</b><p className="text-xs uppercase text-slate-500">{u.role}</p></div><button onClick={()=>active(u)} className={`badge ${u.active?'bg-emerald-500/15 text-emerald-300':'bg-slate-700 text-slate-400'}`}>{u.active?'active':'disabled'}</button></div>)}</div>
      </section>
    </div>
    {selected&&<Evidence data={evidence} job={selectedJob} onBuild={build} busy={building}/>}
  </>;
}


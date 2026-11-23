import {AlertTriangle,LoaderCircle,ShieldCheck} from 'lucide-react';
export function Loading({label='Loading intelligence…'}){return <div className="empty"><LoaderCircle className="mx-auto mb-3 animate-spin text-cyan"/><p>{label}</p></div>}
export function ErrorBox({error}){return error?<div className="error"><AlertTriangle className="mr-2 inline h-4"/>{error}</div>:null}
export function Empty({label='No records match this view.'}){return <div className="empty"><ShieldCheck className="mx-auto mb-3 text-emerald-400"/><p>{label}</p></div>}
export function Severity({value}){const tone=value>=8?'bg-red-500/20 text-red-300':value>=5?'bg-amber-500/20 text-amber-300':'bg-cyan-500/20 text-cyan-300';return <span className={`badge ${tone}`}>S{value}</span>}
export const fmt=(v)=>v?new Date(v).toLocaleString():'—';

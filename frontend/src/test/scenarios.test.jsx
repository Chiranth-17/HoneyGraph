import React from 'react';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import Admin from '../pages/Admin';
import {api} from '../api';

vi.mock('../auth',()=>({useAuth:()=>({session:{token:'test-token',role:'admin'}})}));
vi.mock('../api',()=>({api:vi.fn()}));
beforeEach(()=>{api.mockReset()});
const job={id:'demo-job',name:'lateral_movement',seed:42,status:'awaiting_correlation',deferCorrelation:true};
const evidence={events:[{_id:'event-1',eventType:'lateral_login',deviceId:'camera',protocol:'ssh',payload:{user:'demo'},hash:'abc'}],
  alerts:[{_id:'alert-1',ruleId:'R-LATERAL-06',stage:'lateral-movement',eventIds:['event-1']}],
  incidents:[],counts:{events:1,alerts:1,incidents:0},compassFilters:{events:'{}',alerts:'{}',incidents:'{}'}};

describe('guided scenario presentation',()=>{
  it('launches a run with deferred incident correlation',async()=>{
    api.mockImplementation((path,options)=>Promise.resolve(path==='/users'?[]:path==='/scenarios' ? []:
      path.endsWith('/evidence')?evidence:job));
    render(<MemoryRouter><Admin/></MemoryRouter>);
    fireEvent.click(screen.getByRole('checkbox',{name:/Step-by-step demo/}));
    fireEvent.click(screen.getByRole('button',{name:/Generate events/}));
    await waitFor(()=>expect(api).toHaveBeenCalledWith('/scenarios/launch',expect.objectContaining({body:expect.objectContaining({deferCorrelation:true})})));
  });

  it('shows raw events and alerts while the incident count remains zero',async()=>{
    api.mockImplementation(path=>Promise.resolve(path==='/users'?[]:path==='/scenarios'?[job]:evidence));
    render(<MemoryRouter><Admin/></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button',{name:/Inspect process/}));
    expect(await screen.findByText('event-1')).toBeInTheDocument();
    expect(screen.getByText('alert-1')).toBeInTheDocument();
    expect(screen.getByText(/No incident has been built for this run/)).toBeInTheDocument();
    expect(screen.getByRole('button',{name:/Build incident/})).toBeEnabled();
  });

  it('builds an incident only when the presenter requests it',async()=>{
    api.mockImplementation((path,options)=>Promise.resolve(path==='/users'?[]:path==='/scenarios'?[job]:
      options?.method==='POST'?{...job,status:'completed',incidentIds:['incident-1'],incidentId:'incident-1'}:evidence));
    render(<MemoryRouter><Admin/></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button',{name:/Inspect process/}));
    fireEvent.click(await screen.findByRole('button',{name:/Build incident/}));
    await waitFor(()=>expect(api).toHaveBeenCalledWith('/scenarios/demo-job/correlate',expect.objectContaining({method:'POST'})));
  });
});

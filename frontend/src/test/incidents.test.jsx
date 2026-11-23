import React from 'react';
import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach,describe,expect,it,vi} from 'vitest';
import Incidents from '../pages/Incidents';
import {api} from '../api';

vi.mock('../auth',()=>({useAuth:()=>({session:{token:'test-token',role:'admin'}})}));
vi.mock('../api',()=>({api:vi.fn(),wsUrl:vi.fn()}));
vi.mock('vis-network',()=>({Network:vi.fn(function(){return {destroy:vi.fn()}})}));
const incident={_id:'012345678901234567890123',status:'open',updatedAt:'2026-11-05T00:00:00Z',chain:[],statusHistory:[{status:'open',ts:'2026-11-05T00:00:00Z'}]};
beforeEach(()=>{api.mockReset()});

describe('incident screen recovery',()=>{
  it('shows a failed detail request instead of spinning forever',async()=>{
    api.mockRejectedValue(new Error('incident not found'));
    render(<MemoryRouter initialEntries={['/missing']}><Incidents/></MemoryRouter>);
    expect(await screen.findByText('incident not found')).toBeInTheDocument();
    expect(screen.queryByText('Loading intelligenceÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦')).not.toBeInTheDocument();
  });
  it('ends list loading when a request fails',async()=>{
    api.mockRejectedValue(new Error('backend unavailable'));
    render(<MemoryRouter><Incidents/></MemoryRouter>);
    expect(await screen.findByText('backend unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Loading intelligenceÃƒÂ¢Ã¢â€šÂ¬Ã‚Â¦')).not.toBeInTheDocument();
  });
  it('can refresh the incident list after a scenario completes',async()=>{
    api.mockResolvedValueOnce({items:[],total:0}).mockResolvedValue({items:[incident],total:1});
    render(<MemoryRouter><Incidents/></MemoryRouter>);
    await screen.findByText('No correlated incidents yet.');
    fireEvent.click(screen.getByRole('button',{name:'Refresh'}));
    expect(await screen.findByText('Chain 67890123')).toBeInTheDocument();
  });
  it('disables a status transition while the write is pending',async()=>{
    api.mockImplementation((path,options)=>options?.method==='PATCH'?new Promise(()=>{}):Promise.resolve(incident));
    render(<MemoryRouter initialEntries={['/'+incident._id]}><Incidents/></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button',{name:'Mark triaged'}));
    await waitFor(()=>expect(screen.getByRole('button',{name:/Updating|Mark triaged/})).toBeDisabled());
  });
});

import React from 'react';
import {act,cleanup,render,screen} from '@testing-library/react';
import {afterEach,beforeEach,describe,expect,it,vi} from 'vitest';
import {AuthProvider,useAuth} from '../auth';

function token(exp){return `header.${btoa(JSON.stringify({sub:'admin',exp}))}.signature`}
function Probe(){const {session,message}=useAuth();return <><p>{session?'Authenticated':'Signed out'}</p><p>{message}</p></>}

beforeEach(()=>{localStorage.clear();vi.useFakeTimers();vi.setSystemTime(new Date('2026-11-05T00:00:00Z'))});
afterEach(()=>{cleanup();vi.useRealTimers();localStorage.clear()});

describe('expired dashboard sessions',()=>{
  it('clears an expired saved token and explains why sign-in is required',()=>{
    localStorage.setItem('hg-session',JSON.stringify({token:token(Date.now()/1000-1),role:'admin',username:'admin'}));
    render(<AuthProvider><Probe/></AuthProvider>);
    expect(screen.getByText('Signed out')).toBeInTheDocument();
    expect(screen.getByText(/session expired/i)).toBeInTheDocument();
    expect(localStorage.getItem('hg-session')).toBeNull();
  });

  it('ends an open session when its token expires rather than retrying forever',()=>{
    localStorage.setItem('hg-session',JSON.stringify({token:token(Date.now()/1000+60),role:'admin',username:'admin'}));
    render(<AuthProvider><Probe/></AuthProvider>);
    expect(screen.getByText('Authenticated')).toBeInTheDocument();
    act(()=>vi.advanceTimersByTime(60_000));
    expect(screen.getByText('Signed out')).toBeInTheDocument();
    expect(screen.getByText(/session expired/i)).toBeInTheDocument();
    expect(localStorage.getItem('hg-session')).toBeNull();
  });
});

import {createContext,useCallback,useContext,useEffect,useMemo,useState} from 'react';
import {api} from './api';

const Auth=createContext(null);
const EXPIRED='Your session expired. Please sign in again.';

function tokenExpiry(token){
  // Only used for expiry UX. The backend still verifies signatures and roles.
  try{
    const payload=token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/');
    const {exp}=JSON.parse(atob(payload));
    return typeof exp==='number'&&Number.isFinite(exp)?exp*1000:0;
  }catch{return 0}
}

function savedAuth(){
  try{
    const session=JSON.parse(localStorage.getItem('hg-session'));
    if(!session)return {session:null,message:''};
    return tokenExpiry(session.token)>Date.now()?{session,message:''}:{session:null,message:EXPIRED};
  }catch{return {session:null,message:EXPIRED}}
}

export function AuthProvider({children}){
  const [{session,message},setAuth]=useState(savedAuth);
  const expire=useCallback(()=>{
    localStorage.removeItem('hg-session');
    setAuth({session:null,message:EXPIRED});
  },[]);

  useEffect(()=>{
    if(!session){localStorage.removeItem('hg-session');return}
    let timer;
    function checkExpiry(){
      clearTimeout(timer);
      const remaining=tokenExpiry(session.token)-Date.now();
      if(remaining<=0)expire();
      else timer=setTimeout(checkExpiry,Math.min(remaining,2_147_483_647));
    }
    checkExpiry();
    // Recheck after laptop sleep or a background tab becoming active.
    window.addEventListener('focus',checkExpiry);
    document.addEventListener('visibilitychange',checkExpiry);
    return()=>{
      clearTimeout(timer);
      window.removeEventListener('focus',checkExpiry);
      document.removeEventListener('visibilitychange',checkExpiry);
    };
  },[session,expire]);

  const login=useCallback(async(username,password)=>{
    const next=await api('/auth/login',{method:'POST',body:{username,password}});
    const value={token:next.access_token,role:next.role,username};
    localStorage.setItem('hg-session',JSON.stringify(value));
    setAuth({session:value,message:''});
  },[]);
  const logout=useCallback(()=>{
    localStorage.removeItem('hg-session');
    setAuth({session:null,message:''});
  },[]);
  const value=useMemo(()=>({session,message,login,logout}),[session,message,login,logout]);
  return <Auth.Provider value={value}>{children}</Auth.Provider>;
}
export const useAuth=()=>useContext(Auth);

import type { SagaResult } from './charging'
export function ids(): string[] { try { return JSON.parse(localStorage.getItem('aegisvolt.ids') || '[]') } catch { return [] } }
export function remember(id: string) { localStorage.setItem('aegisvolt.ids', JSON.stringify([id,...ids().filter(x=>x!==id)].slice(0,100))) }
export function cached(): SagaResult[] { try { return JSON.parse(localStorage.getItem('aegisvolt.results') || '[]') } catch { return [] } }
export function save(result: SagaResult) { remember(result.correlation_id); localStorage.setItem('aegisvolt.results',JSON.stringify([result,...cached().filter(x=>x.correlation_id!==result.correlation_id)].slice(0,100))) }
export interface Wallet { fleet_id:string; balance_cents:number; currency:string }
export async function api<T>(path:string, body?:unknown):Promise<T> { const r=await fetch(path,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); if(!r.ok) { const e=await r.json().catch(()=>null); throw new Error(`${r.status}: ${typeof e?.detail==='string'?e.detail:r.statusText}`) } return r.json() }
export const wallet=(id:string)=>api<Wallet>(`/billing/wallets/${encodeURIComponent(id)}`)
export const fund=(id:string,cents:number)=>api<Wallet>(`/billing/wallets/${encodeURIComponent(id)}/funds`,{amount_cents:cents})
export const money=(cents:number,currency='USD')=>new Intl.NumberFormat('es-CO',{style:'currency',currency}).format(cents/100)

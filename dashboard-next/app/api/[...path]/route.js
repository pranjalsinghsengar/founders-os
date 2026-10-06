import {createHmac,timingSafeEqual} from 'node:crypto';
import {NextResponse} from 'next/server';
export const runtime='nodejs';
export const dynamic='force-dynamic';
const getPaths=new Set(['state','artifact','repository']);
const postPaths=new Set(['action','control','pause']);
const equal=(a,b)=>{const x=Buffer.from(a||''),y=Buffer.from(b||'');return x.length===y.length&&timingSafeEqual(x,y)};
function settings(){
 const token=process.env.COMPANY_BRIDGE_TOKEN,origin=process.env.COMPANY_API_ORIGIN,ui=process.env.COMPANY_UI_ORIGIN;
 if(!token||!origin||!ui)return null;
 const backend=new URL(origin),front=new URL(ui);
 if(backend.hostname!=='127.0.0.1'||front.hostname!=='127.0.0.1')return null;
 return {token,origin,front,session:createHmac('sha256',token).update('company-next-browser-session').digest('hex')};
}
function fail(message,status){return NextResponse.json({error:message},{status,headers:{'Cache-Control':'no-store'}})}
async function handle(request,context){
 const config=settings();if(!config)return fail('Start the connected dashboard with company_cli.py dashboard --next',503);
 const host=request.headers.get('host');
 const allowedHosts=new Set([config.front.host,'localhost:'+config.front.port]);
 if(!allowedHosts.has(host)||['cross-site','same-site'].includes(request.headers.get('sec-fetch-site')))return fail('Local same-origin access required',403);
 const path=(await context.params).path?.join('/');const write=request.method==='POST';
 if(!(write?postPaths:getPaths).has(path))return fail('Unknown endpoint',404);
 if(write){
  const origins=new Set([config.front.origin,'http://localhost:'+config.front.port]);
  if(!origins.has(request.headers.get('origin'))||request.headers.get('x-company-ui')!=='1'||!equal(request.cookies.get('company_ui_session')?.value,config.session))return fail('Open dashboard first; local session required',403);
 }
 let body;
 if(write){
  const reader=request.body?.getReader();let size=0;const chunks=[];
  if(!reader)return fail('JSON body required',400);
  while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>60000){await reader.cancel();return fail('Request too large',413)}chunks.push(Buffer.from(value))}
  body=Buffer.concat(chunks);try{JSON.parse(body.toString())}catch{return fail('Invalid JSON',400)}
 }
 try{
  const url=new URL('/api/'+path,config.origin);url.search=new URL(request.url).search;
  const response=await fetch(url,{method:request.method,headers:{'X-Company-Bridge':config.token,...(write?{'Content-Type':'application/json'}:{})},body,cache:'no-store',signal:AbortSignal.timeout(15000)});
  const payload=await response.json();const result=NextResponse.json(payload,{status:response.status,headers:{'Cache-Control':'no-store'}});
  if(!write&&path==='state'&&response.ok)result.cookies.set('company_ui_session',config.session,{httpOnly:true,sameSite:'strict',path:'/'});
  return result;
 }catch{return fail('Python runtime unavailable; check the dashboard terminal',503)}
}
export const GET=handle;
export const POST=handle;

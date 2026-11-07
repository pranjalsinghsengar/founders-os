export function timestamp(value){
 if(typeof value==='number')return Number.isFinite(value)?value*(Math.abs(value)<1e11?1000:1):0;
 if(typeof value!=='string'||!value.trim())return 0;
 const utc=/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value)?value.replace(' ','T')+'Z':value;
 const time=Date.parse(utc);return Number.isFinite(time)?time:0;
}
export function formatTime(value){
 const time=timestamp(value);if(!time)return 'Time not recorded';
 return new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false,timeZoneName:'short'}).format(time);
}
export function newestFirst(list){
 return [...list].sort((a,b)=>timestamp(b.updated_at||b.finished_at||b.at||b.trashed_at||b.created_at)-timestamp(a.updated_at||a.finished_at||a.at||a.trashed_at||a.created_at)||(Number(b.history_sequence||b.id)||0)-(Number(a.history_sequence||a.id)||0));
}

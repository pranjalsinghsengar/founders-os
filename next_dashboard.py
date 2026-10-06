"""One command launches the local Python API and connected Next.js dashboard."""
import os
import secrets
import shutil
import socket
import signal
import subprocess
import threading
from pathlib import Path
from dashboard_server import DashboardServer,initialize

def serve_next(db,config,port=3000,open_browser=False):
 app=Path(__file__).parent/'dashboard-next'
 npm=shutil.which('npm')
 if not npm or not (app/'node_modules/next').exists():raise OSError('Install dashboard-next dependencies before launching')
 with socket.socket() as probe:
  probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
  probe.bind(('127.0.0.1',port))
 initialize(db,config)
 token=secrets.token_urlsafe(48)
 server=DashboardServer(db,config,0,bridge_token=token)
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 env=dict(os.environ)
 env.update({'COMPANY_API_ORIGIN':server.origin,'COMPANY_BRIDGE_TOKEN':token,
             'COMPANY_UI_ORIGIN':f'http://127.0.0.1:{port}','NEXT_TELEMETRY_DISABLED':'1'})
 process=None
 try:
  print(f'Connected Company OS: http://127.0.0.1:{port}',flush=True)
  print('Real workflow state. Provider/email work runs only on explicit actions.',flush=True)
  process=subprocess.Popen([npm,'run','start' if (app/'.next/BUILD_ID').exists() else 'dev','--','--port',str(port)],cwd=app,env=env,start_new_session=True)
  if open_browser:
   import webbrowser
   threading.Timer(2,lambda:webbrowser.open(f'http://127.0.0.1:{port}')).start()
  if process.wait()!=0:raise OSError('Next.js exited; inspect the terminal for the startup error')
 except KeyboardInterrupt:pass
 finally:
  if process:
   try:os.killpg(process.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:process.wait(timeout=8)
   except subprocess.TimeoutExpired:
    try:os.killpg(process.pid,signal.SIGKILL)
    except ProcessLookupError:pass
    process.wait()
  server.shutdown();server.server_close();thread.join()

"""Scheduler active only for workflows explicitly enabled by the founder."""
import threading
import time
import os
from core import Company

class AutonomyService:
    def __init__(self, controls):
        self.controls=controls
        self.stopped=threading.Event()
        self.thread=threading.Thread(target=self.run,daemon=True)
    def start(self):self.thread.start()
    def close(self):
        self.stopped.set()
        self.thread.join(timeout=2)
    def tick(self):
        repair_work=None
        change_action=None
        c=Company(self.controls.db)
        try:
            if c.db.execute("SELECT 1 FROM dashboard_jobs WHERE status IN ('queued','running')").fetchone():return
            import json
            from pathlib import Path
            cfg=json.loads(Path(self.controls.config).read_text())
            if cfg.get('local_recovery_enabled') is True:
                from local_recovery import recover_local
                for failed in c.db.execute("SELECT id FROM tasks WHERE status='failed' AND json_extract(payload,'$.kind')='founder_change'").fetchall():
                    repair_work=recover_local(c,failed['id'],cfg,Path(self.controls.config).resolve().parent)
                    if repair_work:break
            if not repair_work:
                from change_scheduler import next_change_action
                change_action=next_change_action(c,cfg)
            # A killed subprocess leaves a running workflow; never blindly retry its writes/costs.
            with c.transaction():
                if c.db.execute("SELECT 1 FROM dashboard_jobs WHERE status IN ('queued','running')").fetchone():return
                for active in c.db.execute("SELECT id,owner_pid FROM autonomy_runs WHERE status='running'").fetchall():
                    alive=False
                    if active['owner_pid']:
                        try:os.kill(active['owner_pid'],0);alive=True
                        except ProcessLookupError:pass
                        except PermissionError:alive=True
                    if not alive:
                        c.db.execute("UPDATE autonomy_runs SET status='blocked',note='Interrupted handoff; reconcile before restarting' WHERE id=?",(active['id'],))
                from failure_notifications import queue_blocked
                for stopped in c.db.execute("SELECT id,stage,note FROM autonomy_runs WHERE enabled=1 AND status='blocked'").fetchall():
                    if stopped['stage']=='delivery':
                        run=c.db.execute('SELECT project FROM autonomy_runs WHERE id=?',(stopped['id'],)).fetchone()
                        from local_recovery import recover_local
                        recovered=None
                        for failed in c.db.execute("SELECT id FROM tasks WHERE project=? AND status='failed'",(run['project'],)).fetchall():
                            recovered=recover_local(c,failed['id'],cfg,Path(self.controls.config).resolve().parent)
                            if recovered:break
                        if recovered:
                            c.db.execute("UPDATE autonomy_runs SET status='ready',next_at=0,note='Automatic local repair prepared; continuing within existing allowance' WHERE id=?",(stopped['id'],))
                            continue
                    queue_blocked(c,stopped['id'],stopped['stage'],stopped['note'])
            row=c.db.execute("SELECT id FROM autonomy_runs WHERE enabled=1 AND status IN ('ready','waiting_approval') AND next_at<=? ORDER BY updated_at LIMIT 1",(int(time.time()),)).fetchone()
            alert=c.db.execute("SELECT id FROM failure_notifications WHERE status='pending' ORDER BY created_at LIMIT 1").fetchone()
        finally:c.db.close()
        if repair_work:
            self.controls.submit({'action':'run','task':repair_work['task'],'confirmed':True})
            return
        if change_action:
            self.controls.submit(change_action)
            return
        if alert:
            import json
            from pathlib import Path
            cfg=json.loads(Path(self.controls.config).read_text())
            if cfg.get('gmail',{}).get('founder') and cfg.get('gmail',{}).get('token_file'):
                self.controls.submit({'action':'failure-notify','notification':alert['id'],'confirmed':True})
                return
        if row:
            self.controls.submit({'action':'advance-autonomy','workflow':row['id'],'confirmed':True})
    def run(self):
        while not self.stopped.wait(5):
            try:self.tick()
            except Exception:
                # No provider output or credentials enter service logs; safe state remains visible.
                pass

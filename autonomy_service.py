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
        c=Company(self.controls.db)
        try:
            if c.db.execute("SELECT 1 FROM dashboard_jobs WHERE status IN ('queued','running')").fetchone():return
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
            row=c.db.execute("SELECT id FROM autonomy_runs WHERE enabled=1 AND status IN ('ready','waiting_approval') AND next_at<=? ORDER BY updated_at LIMIT 1",(int(time.time()),)).fetchone()
        finally:c.db.close()
        if row:
            self.controls.submit({'action':'advance-autonomy','workflow':row['id'],'confirmed':True})
    def run(self):
        while not self.stopped.wait(5):
            try:self.tick()
            except Exception:
                # No provider output or credentials enter service logs; safe state remains visible.
                pass

import json
import tempfile
from pathlib import Path
from core import Company


def main():
    with tempfile.TemporaryDirectory() as folder:
        path = str(Path(folder) / "company.db")
        c = Company(path)
        project, digest = c.project({"title": "Synthetic product workflow", "scope": "Local demonstration"}, 100)
        c.approve_local(project, digest)
        c.grant(project, "researcher", "local.research")
        c.grant(project, "developer", "local.build")
        c.register_tool("local.research", lambda _: {"artifact": "Synthetic brief", "evidence": "Fixture data; no market research performed"}, 5)
        research = c.task(project, "researcher", "product_manager", "local.research", {})
        c.execute(research)
        c.review(research, "product_manager", True, "Fixture output meets demo criteria")
        build = c.task(project, "developer", "qa", "local.build", {}, [research])
        print("Missing connection:", c.execute(build))
        c.register_tool("local.build", lambda _: {"artifact": "Synthetic build", "evidence": "Fixture test output"}, 10)
        c.execute(build)
        c.review(build, "qa", False, "Demo defect: expected acceptance marker missing")
        c.execute(build)
        c.review(build, "qa", True, "Local review demonstrates successful rework handoff")
        c.db.close()
        resumed = Company(path)
        print(json.dumps(resumed.snapshot(), indent=2))


if __name__ == "__main__":
    main()

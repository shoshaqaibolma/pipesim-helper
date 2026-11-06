"""
Run a list of shell commands, capture all output into runner/last_job.txt, then commit runner/ and
knowledge/ and push, so the cloud session sees the result without anyone copying text.

  "D:\\Program\\Pipesim toolkit\\python.exe" tools\\runner_job.py jobs\\<job>.txt
Each non-empty line of the job file is one command, run from the repo root.
"""
import datetime, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def sh(cmd, timeout=3600):
    p = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main():
    job = sys.argv[1]
    cmds = [l.strip() for l in open(job, encoding="utf-8") if l.strip() and not l.startswith("#")]
    os.makedirs(os.path.join(ROOT, "runner"), exist_ok=True)
    log = [f"JOB {job} started {datetime.datetime.now():%Y-%m-%d %H:%M:%S}"]
    for c in cmds:
        try:
            code, out = sh(c)
        except subprocess.TimeoutExpired:
            code, out = -1, "TIMEOUT"
        log.append(f"\n$ {c}\n[exit {code}]\n{out[-20000:]}")
        print(log[-1][-3000:], flush=True)
    log.append(f"\nJOB finished {datetime.datetime.now():%Y-%m-%d %H:%M:%S}")
    open(os.path.join(ROOT, "runner", "last_job.txt"), "w", encoding="utf-8").write("\n".join(log))
    for c in ("git add runner knowledge", f'git commit -m "Runner results: {os.path.basename(job)}"',
              "git pull --rebase origin claude/pipesim-agent", "git push origin HEAD:claude/pipesim-agent"):
        code, out = sh(c, timeout=300)
        print(f"$ {c} [exit {code}] {out[-500:]}", flush=True)


if __name__ == "__main__":
    main()

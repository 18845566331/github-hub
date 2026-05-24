# new_features.py - Complete module
import os, subprocess, re, json
import urllib.request, urllib.error
import threading
from typing import Optional, Callable, List
from pathlib import Path
BASE = os.path.dirname(os.path.abspath(__file__))
for d in [r"C:\Program Files\Git\cmd", r"C:\Program Files\Git\bin"]:
    if os.path.isdir(d): os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
NL = chr(10)

def list_branches(repo_dir):
    try:
        out = subprocess.check_output(["git","branch","-v"], cwd=repo_dir, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        res = []
        for line in out.strip().split(NL):
            if not line.strip(): continue
            cur = line.strip().startswith("*")
            parts = line.strip().lstrip("* ").split(None, 2)
            res.append({"name":parts[0],"is_current":cur,"commit":parts[1] if len(parts)>1 else "","message":parts[2] if len(parts)>2 else ""})
        return res
    except: return []

def get_current_branch(repo_dir):
    try: return subprocess.check_output(["git","rev-parse","--abbrev-ref","HEAD"], cwd=repo_dir, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0).strip()
    except: return ""

def switch_branch(repo_dir, branch_name, callback=None):
    try:
        p = subprocess.Popen(["git","checkout",branch_name], cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            if callback and line.rstrip(): callback(line.rstrip())
        p.wait(); return p.returncode == 0
    except: return False

def create_branch(repo_dir, branch_name, callback=None):
    try:
        p = subprocess.Popen(["git","checkout","-b",branch_name], cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            if callback and line.rstrip(): callback(line.rstrip())
        p.wait(); return p.returncode == 0
    except: return False

def get_branch_graph(repo_dir, max_count=20):
    try: return subprocess.check_output(["git","log","--graph","--oneline",f"-{max_count}","--all"], cwd=repo_dir, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
    except: return ""

def get_commit_log(repo_dir, branch="HEAD", max_count=50):
    try:
        out = subprocess.check_output(["git","log",branch,f"-{max_count}","--format=%H|%h|%s|%an|%ar"], cwd=repo_dir, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0)
        res = []
        for line in out.strip().split(NL):
            parts = line.split("|",4)
            if len(parts)==5:
                res.append({"hash":parts[0],"short_hash":parts[1],"message":parts[2],"author":parts[3],"date":parts[4]})
        return res
    except: return []

def get_github_actions_status(owner, repo, token=""):
    try:
        headers = {"Accept":"application/vnd.github+json","User-Agent":"GitHubHub/1.0"}
        if token: headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(f"https://api.github.com/repos/{owner}/{repo}/actions/runs?per_page=10", headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            res = []
            for run in data.get("workflow_runs", []):
                res.append({"name":run.get("name",""),"status":run.get("status",""),"conclusion":run.get("conclusion",""),"branch":run.get("head_branch",""),"created_at":str(run.get("created_at",""))[:10],"html_url":run.get("html_url",""),"event":run.get("event","")})
            return res
    except: return []

def create_snapshot(repo_dir, tag_name, message="", callback=None):
    try:
        subprocess.run(["git","tag","-a",tag_name,"-m",message or f"Snapshot: {tag_name}"], cwd=repo_dir, check=True, capture_output=True)
        if callback: callback(f"[SUCCESS] Snapshot: {tag_name}")
        return True
    except: return False

def list_snapshots(repo_dir):
    try:
        out = subprocess.check_output(["git","tag","-l","--sort=-creatordate","--format=%(refname:short)|%(subject)|%(creatordate:short)|%(authorname)"], cwd=repo_dir, text=True, encoding="utf-8", errors="replace")
        res = []
        for line in out.strip().split(NL):
            if not line.strip(): continue
            parts = line.split("|",3)
            res.append({"name":parts[0],"message":parts[1] if len(parts)>1 else "","date":parts[2] if len(parts)>2 else "","author":parts[3] if len(parts)>3 else ""})
        return res
    except: return []

def restore_snapshot(repo_dir, tag_name, callback=None):
    try:
        p = subprocess.Popen(["git","checkout",tag_name], cwd=repo_dir, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            if callback and line.rstrip(): callback(line.rstrip())
        p.wait(); return p.returncode == 0
    except: return False

def delete_snapshot(repo_dir, tag_name, callback=None):
    try:
        subprocess.run(["git","tag","-d",tag_name], cwd=repo_dir, check=True, capture_output=True)
        if callback: callback(f"[SUCCESS] Deleted: {tag_name}"); return True
    except: return False

def parse_help_args(project_dir, python_exe):
    s = []
    for n in ["main.py","app.py","run.py","server.py","cli.py"]:
        fp = os.path.join(project_dir, n)
        if not os.path.exists(fp): continue
        try:
            out = subprocess.check_output([python_exe,n,"--help"], cwd=project_dir, text=True, encoding="utf-8", errors="replace", stderr=subprocess.STDOUT, timeout=10)
            for line in out.split(NL):
                line = line.strip()
                if line.startswith("--"):
                    arg = line.split()[0]
                    if arg not in s: s.append(arg)
                elif line.startswith("-") and not line.startswith("---"):
                    arg = line.split()[0]
                    if arg not in s: s.append(arg)
        except: continue
    return s

class AIAssistant:
    @staticmethod
    def generate_commit_message(diff_text):
        if not diff_text: return "chore: update"
        l = diff_text.strip().split(NL)
        added = [x for x in l if x.startswith("+") and not x.startswith("+++")]
        removed = [x for x in l if x.startswith("-") and not x.startswith("---")]
        changed = [x.replace("diff --git a/","").split(" b/")[0] for x in l if x.startswith("diff --git")]
        p = []
        for f in changed[:3]:
            if added: p.append(f"feat({os.path.basename(f)}): update")
            elif removed: p.append(f"fix({os.path.basename(f)}): cleanup")
        if not p: p.append(f"chore: update ({len(added)}+, {len(removed)}- in {len(changed)} file(s))")
        return "; ".join(p[:2])

    @staticmethod
    def review_code(code):
        issues = []
        for i, line in enumerate(code.split(NL), 1):
            s = line.strip()
            if s.startswith("# TODO"): issues.append({"line":i,"severity":"info","message":f"TODO: {s}"})
            if "print(" in s and not s.startswith("#"): issues.append({"line":i,"severity":"warning","message":"print() in production code"})
            if len(s) > 200: issues.append({"line":i,"severity":"warning","message":f"Line too long ({len(s)} chars)"})
            if "except: pass" in s: issues.append({"line":i,"severity":"error","message":"Bare except:pass"})
        if not issues: issues.append({"line":0,"severity":"info","message":"No obvious issues"})
        return issues

    @staticmethod
    def suggest_variable_name(name):
        m = {"x":"index/count","tmp":"temporary","data":"payload","res":"result","arr":"items","obj":"instance","cb":"callback","ctx":"context","cfg":"config"}
        return m.get(name.lower(), "")

class PluginInfo:
    def __init__(self, data):
        self.name = data.get("name","")
        self.description = data.get("description","")
        self.version = data.get("version","1.0.0")
        self.author = data.get("author","")
        self.repo = data.get("repo","")
        self.type = data.get("type","hook")
        self.entry = data.get("entry","")
        self.enabled = data.get("enabled",False)

def fetch_plugin_registry():
    try:
        req = urllib.request.Request("https://raw.githubusercontent.com/antigravity-ai/githug-plugins/main/registry.json", headers={"User-Agent":"GitHubHub/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return [PluginInfo(item) for item in json.loads(resp.read().decode("utf-8"))]
    except: return []

def load_local_plugins(plugins_dir):
    if not os.path.isdir(plugins_dir): return []
    res = []
    for item in os.listdir(plugins_dir):
        cfg = os.path.join(plugins_dir, item, "plugin.json")
        if os.path.isfile(cfg):
            try:
                with open(cfg,"r",encoding="utf-8") as f:
                    p = PluginInfo(json.load(f)); p.enabled = True; res.append(p)
            except: pass
    return res

def update_all_projects(projects, cb=None):
    results = []
    for proj in projects:
        d = proj.get("local_dir","")
        n = proj.get("name","?")
        if not d or not os.path.isdir(d) or not os.path.isdir(os.path.join(d,".git")):
            results.append({"name":n,"success":False,"message":"Not cloned"}); continue
        if cb: cb(f"[INFO] Pulling {n}...")
        try:
            p = subprocess.Popen(["git","pull","--progress"], cwd=d, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                if cb and line.rstrip(): cb(f"  {line.rstrip()}")
            p.wait()
            results.append({"name":n,"success":p.returncode==0,"message":"Updated" if p.returncode==0 else "Failed"})
        except Exception as e:
            results.append({"name":n,"success":False,"message":str(e)})
    return results

def get_local_readme(project_dir):
    p = Path(project_dir)
    for name in ["README.md","README.rst","README.txt","README"]:
        path = p / name
        if path.exists():
            try: return path.read_text(encoding="utf-8", errors="replace")
            except: pass
    return ""

def render_markdown(md_text):
    if not md_text: return "<p>No README</p>"
    ic = False; html = []
    for line in md_text.split(NL):
        s = line.strip()
        if s.startswith("```"):
            html.append("</code></pre>" if ic else "<pre><code>"); ic = not ic; continue
        if ic: html.append(line.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")+chr(10)); continue
        if s.startswith("# "): html.append(f"<h1>{s[2:]}</h1>")
        elif s.startswith("## "): html.append(f"<h2>{s[3:]}</h2>")
        elif s.startswith("- "): html.append(f"<li>{s[2:]}</li>")
        elif s: html.append(f"<p>{s}</p>")
    if ic: html.append("</code></pre>")
    return "".join(html)

def get_git_diff(repo_dir):
    try:
        out = subprocess.check_output(["git","diff","--cached"], cwd=repo_dir, text=True, encoding="utf-8", errors="replace")
        if not out.strip(): out = subprocess.check_output(["git","diff"], cwd=repo_dir, text=True, encoding="utf-8", errors="replace")
        return out
    except: return ""

print("all features loaded")

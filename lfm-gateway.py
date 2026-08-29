#!/usr/bin/env python3
"""
LFM Gateway — Unified API for all LFM stacks
Routes inference requests across tiers, integrates with Physis coherence.

Stacks:
  /v1/fast      → LFM2.5 standalone (tool calls, trivial tasks)
  /v1/default   → ornith (daily coding, reasoning)
  /v1/heavy     → qwen3.8-27b (complex reasoning, RPC split)
  /v1/toolcall  → LFM2.5 + ornith pair (fast agent loop)
  /v1/swarm     → N LFM2.5 agents + ornith coordinator
  /v1/notebook  → Physis classify + llmwiki search + ornith synthesis
  /v1/axiom     → Praxis API + Physis + LLM integration
"""

import argparse
import json
import os
import subprocess
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import requests

# ── Configuration ─────────────────────────────────────────
LFM_FAST = "http://127.0.0.1:8080"      # LFM2.5 standalone
LFM_DEFAULT = "http://127.0.0.1:8080"   # ornith
LFM_HEAVY = "http://127.0.0.1:8080"     # qwen3.8-27b (when started)
LFM_TOOLCALL = "http://127.0.0.1:8080"  # router
PHYSIS = "http://127.0.0.1:19876"
LLMWIKI = "/home/gio/.local/bin/llmwiki"

# ── Physis client ────────────────────────────────────────
class PhysisClient:
    def __init__(self, base_url=PHYSIS):
        self.base = base_url
    
    def classify(self, text, max_results=3):
        try:
            r = requests.post(f"{self.base}/api/v1/classify", json={"text": text, "max": max_results}, timeout=10)
            return r.json() if r.status_code == 200 else None
        except:
            return None
    
    def register_coherence(self, label, verdict=None):
        try:
            payload = {"input": label}
            if verdict is not None:
                payload["coherence_score"] = verdict
            r = requests.post(f"{self.base}/api/v1/coherence/register", json=payload, timeout=10)
            return r.json() if r.status_code == 200 else None
        except:
            return None
    
    def search_nodes(self, query, token_budget=600, top_k=10):
        try:
            r = requests.post(f"{self.base}/api/v1/search/nodes", json={"query": query, "token_budget": token_budget, "top_k": top_k}, timeout=10)
            return r.json() if r.status_code == 200 else None
        except:
            return None
    
    def ask(self, question, user_id=None):
        try:
            headers = {}
            if user_id:
                headers["X-Physis-User"] = user_id
            r = requests.post(f"{self.base}/api/v1/ask", json={"question": question}, headers=headers, timeout=30)
            return r.json() if r.status_code == 200 else None
        except:
            return None
    
    def health(self):
        try:
            r = requests.get(f"{self.base}/health", timeout=5)
            return r.text
        except:
            return None

# ── Swarm Runner ──────────────────────────────────────────
class SwarmRunner:
    """Spawns N LFM2.5 agents in parallel, coordinates with ornith."""
    
    def __init__(self, n_agents=4, lfm_url=LFM_FAST, ornith_url=LFM_DEFAULT):
        self.n_agents = n_agents
        self.lfm_url = lfm_url
        self.ornith_url = ornith_url
    
    def run_task(self, task, agent_prompts=None):
        """Distribute a task across N agents, collect results, synthesize."""
        if agent_prompts is None:
            agent_prompts = [f"You are agent {i+1} of {self.n_agents}. Solve this task: {task}" for i in range(self.n_agents)]
        
        results = []
        threads = []
        
        def run_agent(prompt, idx):
            try:
                r = requests.post(f"{self.lfm_url}/v1/chat/completions", json={
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 512,
                    "temperature": 0.7
                }, timeout=60)
                if r.status_code == 200:
                    results.append({"agent": idx, "response": r.json()["choices"][0]["message"]["content"]})
            except Exception as e:
                results.append({"agent": idx, "error": str(e)})
        
        for i, prompt in enumerate(agent_prompts[:self.n_agents]):
            t = threading.Thread(target=run_agent, args=(prompt, i))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join(timeout=90)
        
        # Synthesize with ornith
        synthesis = self._synthesize(results, task)
        return {"agents": results, "synthesis": synthesis}
    
    def _synthesize(self, results, task):
        """Use ornith to synthesize swarm results."""
        try:
            prompt = f"Synthesize these agent responses to the task '{task}':\n\n"
            for r in results:
                if "response" in r:
                    prompt += f"Agent {r['agent']+1}: {r['response']}\n\n"
            prompt += "\nProvide a single coherent answer that integrates the best insights."
            
            r = requests.post(f"{self.ornith_url}/v1/chat/completions", json={
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1024
            }, timeout=120)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
        except:
            pass
        return None

# ── Notebook Stack ───────────────────────────────────────
class NotebookStack:
    """Physis classify + llmwiki search + ornith synthesis."""
    
    def __init__(self, physis=PhysisClient()):
        self.physis = physis
    
    def process_note(self, text, user_id=None):
        """Classify note with Physis, search related content, synthesize."""
        classification = self.physis.classify(text)
        
        # Search for related notes via llmwiki
        related = self._search_notes(text)
        
        return {
            "classification": classification,
            "related_notes": related,
            "text": text[:200]
        }
    
    def _search_notes(self, query):
        """Search local notes via llmwiki."""
        try:
            result = subprocess.run([LLMWIKI, "search", query], capture_output=True, text=True, timeout=30)
            return result.stdout[:1000] if result.returncode == 0 else None
        except:
            return None
    
    def ask_knowledge(self, question, user_id=None):
        """Ask Physis (uses LLM cascade with graph retrieval)."""
        return self.physis.ask(question, user_id)

# ── Axiom Stack (Praxis Integration) ─────────────────────
class AxiomStack:
    """Integrates LFM farm + Physis into Praxis webapp.
    
    Called by Praxis backend via API.
    """
    
    def __init__(self, physis=PhysisClient()):
        self.physis = physis
        self.notebook = NotebookStack(physis)
    
    def daily_brief(self, user_id):
        """Generate daily brief: Physis PDCA plan + LLM synthesis."""
        # Get PDCA plan from Physis
        try:
            r = requests.get(f"{PHYSIS}/api/v1/pdca/plan", headers={"X-Physis-User": user_id}, timeout=10)
            pdca = r.json() if r.status_code == 200 else None
        except:
            pdca = None
        
        # Get coherence snapshot
        try:
            r = requests.get(f"{PHYSIS}/api/v1/coherence/snapshot", headers={"X-Physis-User": user_id}, timeout=10)
            coherence = r.json() if r.status_code == 200 else None
        except:
            coherence = None
        
        # Generate brief text via LLM
        brief = self._generate_brief(pdca, coherence)
        
        return {
            "brief": brief,
            "pdca": pdca,
            "coherence": coherence,
            "timestamp": time.time()
        }
    
    def _generate_brief(self, pdca, coherence):
        """Generate daily brief text via LLM."""
        prompt = "Write a short, actionable daily brief for the user.\n\n"
        if pdca:
            prompt += f"PDCA Plan: {json.dumps(pdca, indent=2)}\n\n"
        if coherence:
            prompt += f"Coherence: {json.dumps(coherence, indent=2)}\n\n"
        prompt += "Format: 3 priority tasks, 1 reflection question, 1 habit to reinforce."
        
        try:
            r = requests.post(f"{LFM_FAST}/v1/chat/completions", json={
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512
            }, timeout=60)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
        except:
            pass
        return "Daily brief unavailable — Physis or LLM offline."
    
    def process_tool_call(self, user_id, tool_name, params):
        """Execute a tool call via LFM2.5 + track in Physis."""
        # Execute tool via LLM
        try:
            r = requests.post(f"{LFM_TOOLCALL}/v1/chat/completions", json={
                "messages": [{"role": "user", "content": f"Call tool {tool_name} with params {json(params)}"}],
                "tools": [{"type": "function", "function": {"name": tool_name, "parameters": params}}]
            }, timeout=60)
            result = r.json() if r.status_code == 200 else {"error": "LLM unavailable"}
        except:
            result = {"error": "Request failed"}
        
        # Track in Physis
        self.physis.register_coherence(f"tool_call:{tool_name}", verdict=1.0 if "error" not in result else -1.0)
        
        return result

# ── HTTP Handler ──────────────────────────────────────────
class GatewayHandler(BaseHTTPRequestHandler):
    """Routes requests to the appropriate stack."""
    
    physis = PhysisClient()
    swarm = SwarmRunner()
    notebook = NotebookStack(physis)
    axiom = AxiomStack(physis)
    
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == "/health":
            self._json(200, {
                "status": "ok",
                "stacks": ["fast", "default", "heavy", "toolcall", "swarm", "notebook", "axiom"],
                "services": {
                    "lfm_fast": self._check(LFM_FAST),
                    "lfm_default": self._check(LFM_DEFAULT),
                    "physis": self._check(PHYSIS)
                }
            })
        
        elif parsed.path == "/v1/swarm/status":
            self._json(200, {"agents": self.swarm.n_agents, "lfm": self.swarm.lfm_url, "ornith": self.swarm.ornith_url})
        
        elif parsed.path == "/v1/notebook/classify":
            text = parse_qs(parsed.query).get("text", [""])[0]
            result = self.physis.classify(text)
            self._json(200, result or {"error": "Physis unavailable"})
        
        else:
            self._json(404, {"error": "not found"})
    
    def do_POST(self):
        parsed = urlparse(self.path)
        body = self._read_body()
        
        # ── Direct LLM routes ─────────────────────────────
        if parsed.path == "/v1/fast/chat":
            self._proxy(LFM_FAST, body)
        elif parsed.path == "/v1/default/chat":
            self._proxy(LFM_DEFAULT, body)
        elif parsed.path == "/v1/heavy/chat":
            self._proxy(LFM_HEAVY, body)
        elif parsed.path == "/v1/toolcall/chat":
            self._proxy(LFM_TOOLCALL, body)
        
        # ── Swarm route ───────────────────────────────────
        elif parsed.path == "/v1/swarm/run":
            task = body.get("task", "")
            n = body.get("n_agents", 4)
            self.swarm.n_agents = n
            result = self.swarm.run_task(task)
            self._json(200, result)
        
        # ── Notebook routes ───────────────────────────────
        elif parsed.path == "/v1/notebook/process":
            text = body.get("text", "")
            user_id = body.get("user_id")
            result = self.notebook.process_note(text, user_id)
            self._json(200, result)
        elif parsed.path == "/v1/notebook/ask":
            question = body.get("question", "")
            user_id = body.get("user_id")
            result = self.notebook.ask_knowledge(question, user_id)
            self._json(200, result or {"error": "Physis unavailable"})
        
        # ── Axiom routes ──────────────────────────────────
        elif parsed.path == "/v1/axiom/daily-brief":
            user_id = body.get("user_id", "default")
            result = self.axiom.daily_brief(user_id)
            self._json(200, result)
        elif parsed.path == "/v1/axiom/tool-call":
            user_id = body.get("user_id", "default")
            tool_name = body.get("tool", "")
            params = body.get("params", {})
            result = self.axiom.process_tool_call(user_id, tool_name, params)
            self._json(200, result)
        
        # ── Physis passthrough ────────────────────────────
        elif parsed.path.startswith("/v1/physis/"):
            engine_path = parsed.path[len("/v1/physis"):]
            try:
                r = requests.post(f"{PHYSIS}{engine_path}", json=body, timeout=30)
                self._json(r.status_code, r.json())
            except:
                self._json(502, {"error": "Physis unavailable"})
        
        else:
            self._json(404, {"error": "not found", "path": parsed.path})
    
    def _proxy(self, target, body):
        """Proxy request to LLM server."""
        try:
            r = requests.post(f"{target}/v1/chat/completions", json=body, timeout=120)
            self._json(r.status_code, r.json())
        except Exception as e:
            self._json(502, {"error": str(e)})
    
    def _check(self, url):
        try:
            r = requests.get(f"{url}/health", timeout=3)
            return r.status_code == 200
        except:
            return False
    
    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return json.loads(self.rfile.read(length))
        return {}
    
    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def log_message(self, format, *args):
        pass

def main():
    parser = argparse.ArgumentParser(description="LFM Gateway")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    
    print(f"[lfm-gateway] listening on :{args.port}")
    print(f"[lfm-gateway] fast: {LFM_FAST}")
    print(f"[lfm-gateway] default: {LFM_DEFAULT}")
    print(f"[lfm-gateway] toolcall: {LFM_TOOLCALL}")
    print(f"[lfm-gateway] physis: {PHYSIS}")
    
    server = HTTPServer(("127.0.0.1", args.port), GatewayHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[lfm-gateway] shutting down")
        server.shutdown()

if __name__ == "__main__":
    main()

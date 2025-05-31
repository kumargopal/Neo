#!/usr/bin/env python3
import uuid
import json
import os
import logging
import asyncio
from typing import Dict, List, Any, Optional

# FastAPI imports
from fastapi import FastAPI, WebSocket, BackgroundTasks, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect

# Neuro imports
from core.brain import Brain
from core.pubsub import hub

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Neuro Server")

# Allow all origins for testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage of Brain instances per conversation
brains: Dict[str, Brain] = {}

# ----------------------------------------------------------------------------------
# Neuro API Endpoints
# ----------------------------------------------------------------------------------

# Monkey patch the Executor.run method to explicitly emit replies
from core.executor import Executor

_original_run = Executor.run

async def _patched_run(self):
    conv = self.state.get("__conv")   # may be None in tests
    node  = self.flow["start"]
    nodes = self.flow["nodes"]

    # Wrap the pub method to intercept 'assistant' messages
    original_pub = self.pub
    async def pub_wrapper(topic, data):
        """
        The Executor already publishes any assistant reply; emitting another
        one here causes duplicate panels in the CLI.  Therefore we now simply
        relay every node.* event unchanged.
        """
        await original_pub(topic, data)
    
    self.pub = pub_wrapper
    
    while node:
        spec = nodes[node]                        # {neuro, params, next}
        await self.pub("node.start", {"id": node, "neuro": spec["neuro"]})
        try:
            out = await self.factory.run(
                spec["neuro"],
                self.state,
                **spec.get("params", {}),
            )
            self.state.update(out)
        except Exception as e:
            # ❶ standardised error payload
            err_obj = {
                "error": type(e).__name__,
                "message": str(e),
            }
            # ❷ push a visible assistant message
            await hub.queue(self.state.get("__cid", "default")).put({
                "topic": "assistant",
                "data": f"⚠️ {spec['neuro']} failed: {e}",
            })
            # ❸ still emit node.done so the client's wait logic un-blocks
            await self.pub("node.done", {"id": node, "out": err_obj})
            # ❹ re-raise so Executor/run() can abort the remaining DAG cleanly
            raise
        if conv and "reply" in out and isinstance(out["reply"], str):
            conv.add("assistant", out["reply"])
            await self.pub("assistant", out["reply"])   # 🔥 send to clients
        await self.pub("node.done", {"id": node, "out": out})
        node = spec.get("next")

# Apply the monkey patch
Executor.run = _patched_run

async def _handle_and_emit(cid: str, text: str):
    """Run Brain.handle and push its textual reply (if any) to the hub."""
    brain = brains.setdefault(cid, Brain())
    
    # Use try-except to handle any errors in the brain processing
    try:
        logger.info(f"Processing message from {cid}: {text}")
        reply = await brain.handle(cid, text)
        logger.info(f"Brain reply for {cid}: {reply}")
        
        if reply:
            q = hub.queue(cid)
            # Make sure to properly format and send the assistant message
            await q.put({"topic": "assistant", "data": reply})
            logger.info(f"Sent assistant message to {cid}")
            
            # Only send task.done for immediate replies (not for async tasks)
            if not reply.startswith("🚀"):
                await q.put({"topic": "task.done", "data": {}})
                logger.info(f"Sent task.done for {cid} (immediate reply)")
    except Exception as e:
        logger.error(f"Error processing message for {cid}: {str(e)}")
        # Notify the client of the error
        q = hub.queue(cid)
        await q.put({"topic": "assistant", "data": f"Error processing your request: {str(e)}"})


@app.post("/chat")
async def chat(body: dict, bt: BackgroundTasks):
    cid = body.get("cid") or uuid.uuid4().hex
    text = body["text"]
    # publish user message event
    await hub.queue(cid).put({"topic": "user", "data": text})
    # handle asynchronously and emit reply when done
    bt.add_task(_handle_and_emit, cid, text)
    return {"cid": cid}

@app.websocket("/ws/{cid}")
async def websocket_endpoint(ws: WebSocket, cid: str):
    logger.info(f"WebSocket connection requested for conversation: {cid}")
    await ws.accept()
    logger.info(f"WebSocket connection accepted for conversation: {cid}")
    q = hub.queue(cid)
    try:
        # Send initial connection confirmation
        await ws.send_text(json.dumps({"topic": "system", "data": "Connected to Neuro"}))
        logger.info(f"Sent initial connection message to client: {cid}")
        
        while True:
            ev = await q.get()
            logger.info(f"Sending event to client {cid}: {ev['topic']}")
            await ws.send_text(json.dumps(ev, default=str, ensure_ascii=False))
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for conversation: {cid}")
    except Exception as e:
        logger.error(f"Error in WebSocket handling for {cid}: {str(e)}")
    finally:
        logger.info(f"WebSocket connection closed for conversation: {cid}")

@app.get("/", response_class=HTMLResponse)
async def home():
    """Simple home page with usage instructions"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Neuro Server</title>
        <style>
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                max-width: 900px; 
                margin: 0 auto; 
                padding: 30px; 
                background-color: #0f172a;
                color: #e2e8f0; 
            }
            h1, h2, h3 { 
                color: #f1f5f9; 
                border-bottom: 1px solid #334155;
                padding-bottom: 10px;
            }
            h1 { 
                font-size: 2.5em; 
                background: linear-gradient(to right, #4f46e5, #10b981);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 40px;
            }
            .section {
                background-color: rgba(30, 41, 59, 0.8);
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 30px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }
            .endpoints {
                display: grid;
                grid-template-columns: 1fr;
                gap: 20px;
            }
            .endpoint { 
                background-color: rgba(15, 23, 42, 0.8);
                border-radius: 8px;
                padding: 15px; 
                margin-bottom: 15px; 
                border-left: 4px solid #4f46e5;
            }
            pre { 
                background-color: #1e293b; 
                padding: 12px; 
                border-radius: 5px; 
                overflow: auto;
                color: #94a3b8;
            }
            code {
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 0.9em;
            }
            .tag {
                display: inline-block;
                padding: 2px 8px;
                margin-right: 5px;
                border-radius: 4px;
                font-size: 0.8em;
                font-weight: bold;
            }
            .tag.get {
                background-color: #3b82f6;
                color: white;
            }
            .tag.post {
                background-color: #22c55e;
                color: white;
            }
            .tag.ws {
                background-color: #8b5cf6;
                color: white;
            }
        </style>
    </head>
    <body>
        <h1>Neuro Server</h1>
        
        <div class="section">
            <h2>Overview</h2>
            <p>This server provides chat and brain functionalities for the Neuro.</p>
        </div>
        
        <div class="section">
            <h2>API Endpoints</h2>
            <div class="endpoints">
                <div>
                    <h3>Neuro Server</h3>
                    <div class="endpoint">
                        <span class="tag post">POST</span> <code>/chat</code>
                        <p>Send a chat message to the Neuro brain</p>
                        <p><strong>Body:</strong></p>
                        <pre>{
  "cid": "conversation_id", // optional
  "text": "Your message here"
}</pre>
                    </div>
                    
                    <div class="endpoint">
                        <span class="tag ws">WS</span> <code>/ws/{cid}</code>
                        <p>WebSocket connection for real-time updates</p>
                        <p>Connect to this endpoint to receive events from the Neuro brain.</p>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>Using with CLI Client</h2>
            <p>Run the <code>cli_client.py</code> script to connect to this server:</p>
            <pre>python cli_client.py --host localhost --port 8000</pre>
        </div>
    </body>
    </html>
    """

# ----------------------------------------------------------------------------------
# Main execution
# ----------------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        # watch these dirs (you can add others)
        reload_dirs=[".", "neuros", "core", "profiles"],
        # include .py, .json, and .txt files too
        reload_includes=["*.py", "*.json", "*.txt"],
        # ignore generated or heavy folders
        reload_excludes=[
            "conversations/*",
            "**/__pycache__/*"
        ],
        # give a small pause on reload so clients get time to reconnect
        reload_delay=0.5,
    )

import asyncio, io, json, socket, threading, time
import tkinter as tk
from PIL import Image, ImageTk

try:
    from websockets.asyncio.server import serve as ws_serve
except ImportError:
    from websockets import serve as ws_serve

# ---------- CONFIG ----------
PORT        = 8765
HEALTH_PORT = 8766
MAX_FRAME   = 8 * 1024 * 1024
VIEW_FPS    = 25
MOVE_HZ     = 60
LOG_CTRL    = True
# ----------------------------

agents = {}
lock   = threading.Lock()
selected_id  = {"v": None}
control_mode = {"v": False}
main_loop_ref = {"loop": None}

NAMED_KEYS = {
    "Return", "KP_Enter", "BackSpace", "Tab", "Escape", "Delete", "Insert",
    "Home", "End", "Prior", "Next", "Up", "Down", "Left", "Right",
    "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
    "Super_L", "Super_R", "Caps_Lock",
    "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12",
}


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def local_ips():
    ips = set()
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ips.add(s.getsockname()[0]); s.close()
    except Exception:
        pass
    return sorted(ips)


async def send_to_selected(msg: dict):
    with lock:
        aid = selected_id["v"]
        info = agents.get(aid)
        if info is None:
            if LOG_CTRL: log("[CTRL] no agent selected")
            return
        ws, ctrl, name = info.get("ws"), info.get("control", False), info.get("name", aid)
    if not ws:
        if LOG_CTRL: log(f"[CTRL] no ws for {name}")
        return
    if not ctrl:
        if LOG_CTRL: log(f"[CTRL] {name} has NOT granted control")
        return
    try:
        await ws.send(json.dumps(msg))
        if LOG_CTRL and msg.get("type") != "mouse_move":
            log(f"[CTRL→] {name} {msg}")
    except Exception as e:
        log(f"[CTRL] send fail: {e}")


def fire(msg: dict):
    loop = main_loop_ref["loop"]
    if not (loop and loop.is_running()):
        if LOG_CTRL: log("[CTRL] ws loop not ready yet")
        return
    asyncio.run_coroutine_threadsafe(send_to_selected(msg), loop)


def send_raw(aid, msg):
    with lock:
        ws = agents.get(aid, {}).get("ws")
    loop = main_loop_ref["loop"]
    if ws and loop and loop.is_running():
        asyncio.run_coroutine_threadsafe(ws.send(json.dumps(msg)), loop)
        return True
    return False


# ---------------- ws handler ----------------
async def ws_handler(ws):
    peer_ip = "?"
    try: peer_ip = ws.remote_address[0]
    except Exception: pass
    agent_id = None
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=15)
        if isinstance(raw, bytes): raw = raw.decode("utf-8", errors="ignore")
        hello = json.loads(raw)
        agent_id = hello.get("id") or peer_ip
        name = hello.get("name", agent_id)
        ctrl = bool(hello.get("control_granted", False))
        w = int(hello.get("width", 1920)); h = int(hello.get("height", 1080))
        with lock:
            agents[agent_id] = {"frame": None, "last": time.time(), "name": name,
                                "ip": peer_ip, "ws": ws, "control": ctrl, "size": (w, h)}
            if selected_id["v"] is None:
                selected_id["v"] = agent_id
        log(f"[+] {name} ({peer_ip}) connected control={'YES' if ctrl else 'NO'} {w}x{h}")
        if not ctrl:
            log(f"    {name} chose View only. Use 'Request Control'.")

        async for msg in ws:
            if isinstance(msg, bytes):
                with lock:
                    if agent_id in agents:
                        agents[agent_id]["frame"] = msg
                        agents[agent_id]["last"] = time.time()
            else:
                try: j = json.loads(msg)
                except Exception: continue
                if j.get("type") == "control_status":
                    with lock:
                        if agent_id in agents:
                            agents[agent_id]["control"] = bool(j.get("granted"))
                    log(f"[CTRL] {name} control now {j.get('granted')}")
    except Exception as e:
        log(f"[!] handler {agent_id or peer_ip}: {type(e).__name__}: {e}")
    finally:
        with lock:
            if agent_id in agents and agents[agent_id].get("ws") is ws:
                agents.pop(agent_id, None)
        log(f"[-] {agent_id} disconnected")


async def ws_main():
    main_loop_ref["loop"] = asyncio.get_running_loop()
    log("=" * 60)
    log(f"NetShare WS server listening 0.0.0.0:{PORT}")
    log("Put one of these into agent.py SERVER_HOST:")
    for ip in local_ips(): log(f"    {ip}")
    log("=" * 60)
    try:
        async with ws_serve(ws_handler, "0.0.0.0", PORT, max_size=MAX_FRAME,
                            ping_interval=20, ping_timeout=20):
            await asyncio.Future()
    except OSError as e:
        log(f"[FATAL] bind 0.0.0.0:{PORT} failed — {e}")


async def handle_health(reader, writer):
    try:
        await asyncio.wait_for(reader.read(1024), timeout=3)
        body = b"NetShare OK\n"
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
                     b"Content-Length: " + str(len(body)).encode() +
                     b"\r\nConnection: close\r\n\r\n" + body)
        await writer.drain()
    except Exception:
        pass
    finally:
        try: writer.close()
        except Exception: pass


async def health_main():
    try:
        server = await asyncio.start_server(handle_health, "0.0.0.0", HEALTH_PORT)
    except OSError as e:
        log(f"[warn] health: {e}"); return
    async with server:
        await server.serve_forever()


def start_threads():
    def run_ws():
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        try: loop.run_until_complete(ws_main())
        except Exception as e: log(f"[FATAL] WS: {e}")
    def run_health():
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
        try: loop.run_until_complete(health_main())
        except Exception as e: log(f"[warn] health: {e}")
    threading.Thread(target=run_ws, daemon=True).start()
    threading.Thread(target=run_health, daemon=True).start()


# ================== Viewer GUI ==================
class ViewerApp:
    def __init__(self, root):
        self.root = root
        root.title("NetShare — Viewer")
        root.geometry("1240x780")
        root.configure(bg="#0b1220")

        top = tk.Frame(root, bg="#111c33", height=56)
        top.pack(fill=tk.X); top.pack_propagate(False)
        tk.Label(top, text="🛰️ NetShare Viewer", bg="#111c33", fg="#e2e8f0",
                 font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT, padx=14)

        self.ctrl_var = tk.BooleanVar(value=False)
        self.ctrl_btn = tk.Checkbutton(
            top, text="🎮 Control", variable=self.ctrl_var,
            command=self.toggle_control, bg="#111c33", fg="#f59e0b",
            selectcolor="#111c33", activebackground="#111c33",
            activeforeground="#f59e0b", font=("Segoe UI", 11, "bold"),
            bd=0, highlightthickness=0)
        self.ctrl_btn.pack(side=tk.LEFT, padx=20)

        self.req_btn = tk.Button(top, text="Request Control", command=self.request_control,
                                 bg="#1f2e4d", fg="#e2e8f0", relief=tk.FLAT,
                                 font=("Segoe UI", 10))
        self.req_btn.pack(side=tk.LEFT, padx=6)

        self.quality_var = tk.StringVar(value="High")
        tk.Label(top, text="Quality:", bg="#111c33", fg="#7c8db5",
                 font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(20, 4))
        qmenu = tk.OptionMenu(top, self.quality_var, "Low", "Medium", "High",
                              command=self.change_quality)
        qmenu.config(bg="#1f2e4d", fg="#e2e8f0", relief=tk.FLAT,
                     activebackground="#2a3c5e", highlightthickness=0)
        qmenu["menu"].config(bg="#1f2e4d", fg="#e2e8f0")
        qmenu.pack(side=tk.LEFT)

        self.status = tk.Label(top, text="Waiting for agents…", bg="#111c33",
                               fg="#7c8db5", font=("Segoe UI", 10))
        self.status.pack(side=tk.RIGHT, padx=14)

        body = tk.Frame(root, bg="#0b1220"); body.pack(fill=tk.BOTH, expand=True)
        side = tk.Frame(body, bg="#111c33", width=240)
        side.pack(side=tk.LEFT, fill=tk.Y); side.pack_propagate(False)
        tk.Label(side, text="CONNECTED AGENTS", bg="#111c33", fg="#7c8db5",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=12, pady=(14, 6))
        self.listbox = tk.Listbox(side, bg="#0b1220", fg="#e2e8f0",
                                  selectbackground="#1f2e4d", borderwidth=0,
                                  highlightthickness=0, font=("Segoe UI", 10),
                                  activestyle="none", exportselection=False)
        self.listbox.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        right = tk.Frame(body, bg="#000000")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(right, bg="#000000", highlightthickness=0,
                                takefocus=1, cursor="arrow")
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_text(400, 200, text="No frame yet", fill="#334155",
                                font=("Segoe UI", 12), tags="placeholder")

        c = self.canvas
        c.bind("<Motion>", self.on_motion)
        c.bind("<B1-Motion>", self.on_motion)
        c.bind("<B2-Motion>", self.on_motion)
        c.bind("<B3-Motion>", self.on_motion)
        c.bind("<ButtonPress-1>",   lambda e: self.on_button(e, "left", True))
        c.bind("<ButtonRelease-1>", lambda e: self.on_button(e, "left", False))
        c.bind("<ButtonPress-2>",   lambda e: self.on_button(e, "middle", True))
        c.bind("<ButtonRelease-2>", lambda e: self.on_button(e, "middle", False))
        c.bind("<ButtonPress-3>",   lambda e: self.on_button(e, "right", True))
        c.bind("<ButtonRelease-3>", lambda e: self.on_button(e, "right", False))
        c.bind("<MouseWheel>", self.on_wheel)
        c.bind("<Button-4>", lambda e: self.on_wheel_linux(e, 1))    # up
        c.bind("<Button-5>", lambda e: self.on_wheel_linux(e, -1))   # down
        c.bind("<KeyPress>",   lambda e: self.on_key(e, True))
        c.bind("<KeyRelease>", lambda e: self.on_key(e, False))
        c.bind("<Enter>", lambda e: c.focus_set())

        self.tk_img = None
        self.img_offset = (0, 0)
        self.img_dims = (1, 1)
        self.last_list = []
        self.last_move_t = 0.0
        self.canvas_img_id = None
        self.ctrl_down = False
        self.alt_down = False
        self.last_agent_ctrl = None
        root.after(1000 // VIEW_FPS, self.tick)

    def _to_norm(self, x, y):
        ox, oy = self.img_offset
        iw, ih = self.img_dims
        nx = (x - ox) / max(iw, 1)
        ny = (y - oy) / max(ih, 1)
        return (max(0.0, min(1.0, nx)), max(0.0, min(1.0, ny)))

    def on_motion(self, e):
        if not control_mode["v"]: return
        now = time.time()
        if now - self.last_move_t < 1.0 / MOVE_HZ: return
        self.last_move_t = now
        nx, ny = self._to_norm(e.x, e.y)
        fire({"type": "mouse_move", "x": nx, "y": ny})

    def on_button(self, e, button, pressed):
        if not control_mode["v"]: return
        self.canvas.focus_set()
        nx, ny = self._to_norm(e.x, e.y)
        fire({"type": "mouse_move", "x": nx, "y": ny})
        fire({"type": "mouse_button", "button": button, "pressed": pressed})

    def on_wheel(self, e):
        if not control_mode["v"]: return
        fire({"type": "scroll", "dx": 0, "dy": 1 if e.delta > 0 else -1})

    def on_wheel_linux(self, e, direction):
        if not control_mode["v"]: return
        fire({"type": "scroll", "dx": 0, "dy": direction})

    def on_key(self, e, pressed):
        if not control_mode["v"]: return
        ks = e.keysym
        ch = e.char or ""
        if ks in ("Control_L", "Control_R"): self.ctrl_down = pressed
        if ks in ("Alt_L", "Alt_R"):         self.alt_down = pressed

        if ks in NAMED_KEYS:
            fire({"type": "key", "keysym": ks, "pressed": pressed})
            return "break"
        # shortcuts like Ctrl+C / Alt+F4
        if (self.ctrl_down or self.alt_down) and len(ks) == 1:
            fire({"type": "key", "keysym": ks.lower(), "pressed": pressed})
            return "break"
        # normal typing
        if pressed and len(ch) == 1 and ch.isprintable():
            fire({"type": "key_type", "text": ch})
        return "break"

    def toggle_control(self):
        with lock:
            aid = selected_id["v"]
            info = agents.get(aid)
            ctrl = info.get("control", False) if info else False
            name = info.get("name", aid) if info else ""
        if info is None:
            self.ctrl_var.set(False); return
        if self.ctrl_var.get() and not ctrl:
            self.ctrl_var.set(False)
            self.status.config(text=f"{name} hasn't granted control — click Request",
                               fg="#f87171")
            return
        control_mode["v"] = self.ctrl_var.get()
        self.canvas.config(cursor="crosshair" if control_mode["v"] else "arrow")
        if control_mode["v"]: self.canvas.focus_set()
        self.status.config(
            text="🎮 Control ENABLED — click canvas, then move/type" if control_mode["v"]
                 else "View only",
            fg="#f59e0b" if control_mode["v"] else "#7c8db5")
        log(f"[CTRL] local control_mode = {control_mode['v']}")

    def request_control(self):
        aid = selected_id["v"]
        if aid in agents and send_raw(aid, {"type": "request_control"}):
            self.status.config(text="Asked agent for control…", fg="#f59e0b")
            log("[CTRL] requested control")

    def change_quality(self, val):
        presets = {"Low": (0.55, 50, 10), "Medium": (0.75, 70, 15), "High": (0.90, 82, 18)}
        s, q, f = presets[val]
        send_raw(selected_id["v"], {"type": "set_quality", "scale": s, "quality": q, "fps": f})

    def on_select(self, _):
        idx = self.listbox.curselection()
        if not idx: return
        name = self.listbox.get(idx[0]).replace(" 🎮", "").strip()
        with lock:
            for aid, info in agents.items():
                if info["name"] == name:
                    selected_id["v"] = aid
                    break
        self.ctrl_var.set(False); control_mode["v"] = False
        self.canvas.config(cursor="arrow")
        self.canvas_img_id = None
        self.canvas.delete("all")

    def tick(self):
        with lock:
            entries = [(aid, info["name"], info.get("control", False))
                       for aid, info in agents.items()]
            frame, agent_ctrl = None, False
            if selected_id["v"] in agents:
                frame = agents[selected_id["v"]]["frame"]
                agent_ctrl = agents[selected_id["v"]].get("control", False)

        # sync with agent's control state (grant / revoke)
        if agent_ctrl != self.last_agent_ctrl:
            if agent_ctrl:
                self.status.config(text="Agent granted control — tick 🎮 Control", fg="#4ade80")
            elif control_mode["v"]:
                control_mode["v"] = False
                self.ctrl_var.set(False)
                self.canvas.config(cursor="arrow")
                self.status.config(text="Agent revoked control", fg="#f87171")
            self.last_agent_ctrl = agent_ctrl

        sig = [(n, c) for _, n, c in entries]
        if sig != self.last_list:
            self.listbox.delete(0, tk.END)
            for _, name, ctrl in entries:
                self.listbox.insert(tk.END, name + (" 🎮" if ctrl else ""))
            if selected_id["v"] in agents:
                sel = agents[selected_id["v"]]["name"]
                for i, (n, _) in enumerate(sig):
                    if n == sel:
                        self.listbox.selection_clear(0, tk.END)
                        self.listbox.selection_set(i); break
            self.last_list = sig

        if frame:
            try:
                img = Image.open(io.BytesIO(frame))
                cw = max(self.canvas.winfo_width(), 100)
                ch = max(self.canvas.winfo_height(), 100)
                img.thumbnail((cw, ch), Image.LANCZOS)
                iw, ih = img.size
                self.img_dims = (iw, ih)
                ox, oy = (cw - iw) // 2, (ch - ih) // 2
                self.img_offset = (ox, oy)
                self.tk_img = ImageTk.PhotoImage(img)
                if self.canvas_img_id is None:
                    self.canvas.delete("placeholder")
                    self.canvas_img_id = self.canvas.create_image(
                        ox, oy, anchor=tk.NW, image=self.tk_img)
                else:
                    self.canvas.itemconfig(self.canvas_img_id, image=self.tk_img)
                    self.canvas.coords(self.canvas_img_id, ox, oy)
            except Exception as e:
                log(f"[render] {e}")

        self.root.after(1000 // VIEW_FPS, self.tick)


if __name__ == "__main__":
    start_threads()
    root = tk.Tk()
    ViewerApp(root)
    root.mainloop()
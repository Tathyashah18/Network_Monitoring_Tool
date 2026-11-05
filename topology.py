
import os,sys,re,socket,subprocess,json,urllib.parse,ipaddress
import django

BASE_DIR=os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path: sys.path.insert(0,BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE","nms.settings")
django.setup()
from dashboard.models import Device

OUTPUT_FILE=os.path.join(BASE_DIR,"topology.html")

def run_command(command):
    try: return subprocess.check_output(command,encoding="utf-8",errors="ignore")
    except Exception: return ""

def get_local_ip():
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8",80))
            return s.getsockname()[0]
    except Exception: return "127.0.0.1"

def get_network_info():
    output=run_command(["ipconfig"])
    adapters={}
    current=None
    for line in output.splitlines():
        match=re.match(r"^\s*.*adapter\s+(.+):\s*$",line,re.I)
        if match:
            current=match.group(1).strip()
            adapters[current]={"ip":None,"gateway":None}
        elif current:
            match=re.search(r"IPv4 Address[ .]*:\s*([\d.]+)",line,re.I)
            if match: adapters[current]["ip"]=match.group(1)
            match=re.search(r"Default Gateway[ .:]+(\d+\.\d+\.\d+\.\d+)",line,re.I)
            if match: adapters[current]["gateway"]=match.group(1)
    wifi=next((v for k,v in adapters.items() if k.lower()=="wi-fi" and v["ip"]),{})
    hotspot=next((v for k,v in adapters.items() if v["ip"] and ("local area connection*" in k.lower() or "wi-fi direct" in k.lower())),{})
    local_ip=wifi.get("ip") or get_local_ip()
    gateway=wifi.get("gateway") or next((v["gateway"] for v in adapters.values() if v["gateway"]),None)
    hotspot_ip=hotspot.get("ip") or "192.168.137.1"
    try: network=ipaddress.ip_network(f"{hotspot_ip}/24",strict=False)
    except ValueError: network=ipaddress.ip_network("192.168.137.0/24")
    return local_ip,gateway,hotspot_ip,network

def get_arp_table():
    table={}
    for line in run_command(["arp","-a"]).splitlines():
        match=re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F:-]{17})\s+\w+",line)
        if match: table[match.group(1)]=match.group(2)
    return table

def get_hostname(ip):
    try: return socket.gethostbyaddr(ip)[0]
    except Exception: return ""

def determine_device_type(ip,hostname,gateway,mac=""):
    hostname=(hostname or "").lower()
    if gateway and ip==gateway: return "Router"
    if any(x in hostname for x in ["router","gateway","mikrotik","cisco","tp-link","tplink","netgear","asus","dlink"]): return "Router"
    if any(x in hostname for x in ["switch","managed-switch"]): return "Switch"
    if any(x in hostname for x in ["access-point","accesspoint","wifi","wireless","wlan","access point"]): return "Access Point"
    if any(x in hostname for x in ["server","srv","nas","database","db-server","web-server","mail-server","file-server"]): return "Server"
    return "Device"

def build_topology():
    local_ip,gateway,hotspot_ip,hotspot_network=get_network_info()
    arp=get_arp_table()
    nodes=[{"id":"internet","label":"Internet","type":"Internet","level":0,"ip":"","hostname":"Internet","status":"Online","mac":""}]
    edges=[]
    parent="internet"
    if gateway:
        nodes.append({"id":gateway,"label":"Router","type":"Router","level":1,"ip":gateway,"hostname":get_hostname(gateway),"status":"Online","mac":arp.get(gateway,"")})
        edges.append({"from":"internet","to":gateway})
        parent=gateway
    nodes.append({"id":"laptop","label":"My Laptop","type":"Switch","level":2,"ip":local_ip,"hostname":socket.gethostname(),"status":"Online","mac":arp.get(local_ip,"")})
    edges.append({"from":parent,"to":"laptop"})
    for device in Device.objects.all().order_by("ip_address"):
        ip=str(device.ip_address)
        try:
            if ipaddress.ip_address(ip) not in hotspot_network: continue
        except ValueError: continue
        if ip in (hotspot_ip,local_ip,gateway): continue
        hostname=device.hostname or get_hostname(ip)
        mac=device.mac_address or arp.get(ip,"")
        kind=determine_device_type(ip,hostname,gateway,mac)
        status=device.status or "Offline"
        nodes.append({"id":ip,"label":hostname or ip,"type":kind,"level":3,"ip":ip,"hostname":hostname,"status":status,"mac":mac})
        edges.append({"from":"laptop","to":ip})
    return local_ip,gateway,nodes,edges

def create_icon(kind,color):
    shapes={
        "Internet":f'<circle cx="40" cy="40" r="30" fill="white" stroke="{color}" stroke-width="4"/><circle cx="40" cy="40" r="23" fill="none" stroke="{color}" stroke-width="2"/><path d="M17 40h46 M40 17c16 15 16 31 0 46 M40 17c-16 15-16 31 0 46" stroke="{color}" stroke-width="2" fill="none"/>',
        "Router":f'<rect x="12" y="25" width="56" height="30" rx="6" fill="white" stroke="{color}" stroke-width="4"/><path d="M22 34h36 M40 25V15 M30 19l10-4 10 4" stroke="{color}" stroke-width="3" fill="none"/><circle cx="25" cy="46" r="3" fill="{color}"/><circle cx="40" cy="46" r="3" fill="{color}"/><circle cx="55" cy="46" r="3" fill="{color}"/>',
        "Switch":f'<rect x="10" y="25" width="60" height="30" rx="5" fill="white" stroke="{color}" stroke-width="4"/>'+''.join(f'<circle cx="{x}" cy="40" r="3" fill="{color}"/>' for x in [22,34,46,58]),
        "Access Point":f'<circle cx="40" cy="47" r="8" fill="white" stroke="{color}" stroke-width="4"/><path d="M24 35c9-9 23-9 32 0 M16 27c13-13 35-13 48 0 M40 55v11" stroke="{color}" stroke-width="4" fill="none" stroke-linecap="round"/>',
        "Server":f'<rect x="20" y="10" width="40" height="60" rx="5" fill="white" stroke="{color}" stroke-width="4"/>'+''.join(f'<rect x="27" y="{y}" width="26" height="12" rx="2" fill="{color}" opacity=".15"/><circle cx="32" cy="{y+6}" r="2" fill="{color}"/>' for y in [18,35,52])
    }
    svg=shapes.get(kind,f'<rect x="12" y="13" width="56" height="40" rx="4" fill="white" stroke="{color}" stroke-width="4"/><rect x="18" y="19" width="44" height="28" fill="{color}" opacity=".12"/><path d="M28 62h24 M40 53v9" stroke="{color}" stroke-width="4" stroke-linecap="round"/>')
    return "data:image/svg+xml;charset=utf-8,"+urllib.parse.quote(f'<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80" viewBox="0 0 80 80">{svg}</svg>')

def generate_html(local_ip=None,gateway=None,nodes=None,edges=None):
    if nodes is None or edges is None: local_ip,gateway,nodes,edges=build_topology()
    colors={"Internet":"#2563eb","Router":"#dc2626","Switch":"#7c3aed","Access Point":"#059669","Server":"#0891b2","Device":"#2563eb"}
    visual=[]
    for node in nodes:
        kind=node.get("type","Device")
        offline=str(node.get("status","Online")).lower()=="offline" and kind not in ["Internet","Router","Switch","Access Point"]
        online_icon=create_icon(kind,colors.get(kind,"#2563eb"))
        offline_icon=create_icon(kind,"#dc2626")
        visual.append({**node,"shape":"image","image":offline_icon if offline else online_icon,"onlineImage":online_icon,"offlineImage":offline_icon,"deviceType":kind,"deviceStatus":str(node.get("status","Online")).lower(),"size":30,"title":node.get("hostname") or node.get("ip") or node.get("label"),"font":{"size":14,"face":"Arial","color":"#111827"},"borderWidth":4 if offline else 2})
    nj=json.dumps(visual).replace("</","<\\/")
    ej=json.dumps(edges).replace("</","<\\/")
    html=f'''<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Network Topology</title><script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
*{{box-sizing:border-box}}html,body{{margin:0;width:100%;height:100%;font-family:Arial;background:#f8fafc}}body{{overflow:hidden}}.header{{height:75px;background:white;border-bottom:1px solid #d1d5db;display:flex;align-items:center;justify-content:space-between;padding:0 20px}}.header-left,.header-right{{display:flex;align-items:center;gap:12px}}.back-button,.header-button{{border:0;border-radius:7px;padding:10px 14px;text-decoration:none;font-size:13px;font-weight:600;cursor:pointer}}.back-button{{background:#2563eb;color:white}}.header-button{{background:#eef2ff;color:#3730a3}}.title{{font-size:21px;font-weight:700;color:#111827}}.subtitle{{font-size:11px;color:#6b7280;margin-top:4px}}#network{{width:100%;height:calc(100vh - 75px)}}.panel,.legend,.child-panel{{position:absolute;z-index:10;background:#fffffff5;border:1px solid #d1d5db;border-radius:10px;padding:13px;box-shadow:0 4px 12px #0002}}.panel{{top:95px;left:18px;width:190px}}.legend{{top:95px;right:18px;width:175px}}.panel-title{{font-size:13px;font-weight:bold;margin-bottom:10px}}select{{width:100%;padding:9px;border:1px solid #d1d5db;border-radius:6px}}#filterCount{{font-size:11px;color:#6b7280;margin-top:8px}}.legend-item{{display:flex;align-items:center;gap:9px;font-size:12px;margin:8px 0;color:#374151}}.dot{{width:12px;height:12px;border-radius:50%;background:#2563eb}}.red{{background:#dc2626}}.purple{{background:#7c3aed}}.green{{background:#059669}}.child-panel{{display:none;top:95px;right:18px;width:290px;max-height:65vh;overflow:auto;z-index:20;padding:0}}.child-header{{display:flex;justify-content:space-between;padding:14px;border-bottom:1px solid #e5e7eb}}.child-title{{font-weight:bold;font-size:14px}}.child-subtitle{{font-size:11px;color:#6b7280;margin-top:4px}}.child-close{{border:0;border-radius:5px;padding:5px 10px;cursor:pointer}}#childSummary{{padding:10px 14px;font-size:12px;background:#f8fafc}}#childList{{padding:10px}}.child-item{{display:flex;justify-content:space-between;gap:8px;padding:10px;margin-bottom:7px;border:1px solid #e5e7eb;border-radius:7px;cursor:pointer}}.child-item:hover{{background:#eff6ff}}.child-name{{font-size:12px;font-weight:bold;overflow:hidden;text-overflow:ellipsis}}.child-ip{{font-size:10px;color:#6b7280;margin-top:4px}}.child-status{{font-size:10px;white-space:nowrap}}.empty{{padding:15px;text-align:center;font-size:12px;color:#6b7280}}@media(max-width:700px){{.header{{padding:0 8px}}.title{{font-size:16px}}.subtitle{{display:none}}.back-button,.header-button{{padding:8px;font-size:11px}}.panel{{left:8px;width:160px}}.legend{{right:8px;width:150px}}.child-panel{{left:8px;right:8px;width:auto;top:90px}}}}
</style></head><body>
<div class="header"><div class="header-left"><a href="/" class="back-button">← Dashboard</a><div><div class="title">Network Topology</div><div class="subtitle">Internet → Router → My Laptop → Connected Devices</div></div></div><div class="header-right"><button class="header-button" onclick="fitNetwork()">Fit</button><button class="header-button" onclick="location.reload()">Refresh</button></div></div>
<div class="panel"><div class="panel-title">Filter Nodes</div><select id="nodeFilter" onchange="applyFilter()"><option value="all">All Devices</option><option value="online">Online</option><option value="offline">Offline</option><option value="Router">Routers</option><option value="Switch">Switches</option><option value="Access Point">Access Points</option><option value="Server">Servers</option><option value="Device">Devices</option></select><div id="filterCount">Showing all nodes</div></div>
<div class="legend"><div class="panel-title">Legend</div><div class="legend-item"><span class="dot"></span>Internet / Online</div><div class="legend-item"><span class="dot red"></span>Router</div><div class="legend-item"><span class="dot purple"></span>My Laptop</div><div class="legend-item"><span class="dot green"></span>Access Point</div><div class="legend-item"><span class="dot red"></span>Offline Device</div></div>
<div id="childPanel" class="child-panel"><div class="child-header"><div><div id="childTitle" class="child-title"></div><div id="childSubtitle" class="child-subtitle"></div></div><button class="child-close" onclick="closePanel()">×</button></div><div id="childSummary"></div><div id="childList"></div></div><div id="network"></div>
<script>
const initialNodes={nj},initialEdges={ej},allNodes=initialNodes.map(n=>({{...n}})),allEdges=initialEdges.map(e=>({{...e}}));
const nodes=new vis.DataSet(allNodes),edges=new vis.DataSet(allEdges);let selectedParent=null;
const network=new vis.Network(document.getElementById("network"),{{nodes,edges}},{{layout:{{hierarchical:{{enabled:true,direction:"UD",sortMethod:"directed",levelSeparation:145,nodeSpacing:180,treeSpacing:220,blockShifting:true,edgeMinimization:true,parentCentralization:true}}}},physics:{{enabled:false}},interaction:{{hover:true,navigationButtons:true,keyboard:true,zoomView:true,dragView:true}},nodes:{{shape:"image",size:30,borderWidth:2,margin:10,font:{{size:14,face:"Arial",color:"#111827"}}}},edges:{{width:2,color:{{color:"#64748b",highlight:"#2563eb"}},arrows:{{to:{{enabled:true,scaleFactor:.8}}}},smooth:{{type:"cubicBezier",forceDirection:"vertical",roundness:.4}}}}}});
function fitNetwork(){{network.fit({{animation:{{duration:400,easingFunction:"easeInOutQuad"}}}})}}
function escapeHtml(v){{return String(v||"").replace(/[&<>"']/g,c=>({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}}[c]))}}
function getChildren(id){{const ids=allEdges.filter(e=>String(e.from)===String(id)).map(e=>String(e.to));return allNodes.filter(n=>ids.includes(String(n.id)))}}
function visualState(n){{const off=n.deviceStatus==="offline"&&!["Internet","Router","Switch","Access Point"].includes(n.deviceType);return {{image:off?n.offlineImage:n.onlineImage,borderWidth:off?4:2,shadow:{{enabled:off,color:"rgba(220,38,38,.5)",size:16}}}}}}
function edgeState(e){{const a=allNodes.find(n=>String(n.id)===String(e.from)),b=allNodes.find(n=>String(n.id)===String(e.to)),off=[a,b].some(n=>n&&n.deviceStatus==="offline"&&!["Internet","Router","Switch","Access Point"].includes(n.deviceType));return {{color:{{color:off?"#dc2626":"#64748b",highlight:"#2563eb"}},dashes:off?[7,7]:false,width:2}}}}
function showChildren(id,refit=true){{const p=allNodes.find(n=>String(n.id)===String(id));if(!p||!["Router","Switch"].includes(p.deviceType))return;selectedParent=String(id);const children=getChildren(id);document.getElementById("childTitle").textContent=p.label;document.getElementById("childSubtitle").textContent="Directly connected devices";document.getElementById("childSummary").textContent="Connected devices: "+children.length;const list=document.getElementById("childList");list.innerHTML="";if(!children.length)list.innerHTML='<div class="empty">No child devices found.</div>';children.forEach(c=>{{const off=c.deviceStatus==="offline",item=document.createElement("div");item.className="child-item";item.innerHTML='<div><div class="child-name">'+escapeHtml(c.hostname||c.label||c.ip)+'</div><div class="child-ip">'+escapeHtml(c.ip||c.id)+'</div></div><div class="child-status" style="color:'+(off?"#dc2626":"#16a34a")+'">'+(off?"Offline":"Online")+'</div>';item.onclick=()=>{{if(c.ip)location.href="/device/"+encodeURIComponent(c.ip)+"/"}};list.appendChild(item)}});document.getElementById("childPanel").style.display="block";if(refit)network.fit({{nodes:[String(id),...children.map(c=>String(c.id))],animation:{{duration:400}}}})}}
function closePanel(){{document.getElementById("childPanel").style.display="none";selectedParent=null;applyFilter()}}
function applyFilter(){{const f=document.getElementById("nodeFilter").value,infra=["Internet","Router","Switch","Access Point"];const shown=allNodes.filter(n=>f==="all"||(f==="online"?!infra.includes(n.deviceType)&&n.deviceStatus!=="offline":f==="offline"?!infra.includes(n.deviceType)&&n.deviceStatus==="offline":n.deviceType===f));nodes.clear();nodes.add(shown.map(n=>({{...n,...visualState(n)}})));const ids=new Set(shown.map(n=>String(n.id)));edges.clear();edges.add(allEdges.filter(e=>ids.has(String(e.from))&&ids.has(String(e.to))).map(e=>({{...e,...edgeState(e)}})));document.getElementById("filterCount").textContent=f==="all"?"Showing all nodes":"Showing "+shown.length+" node(s)";if(selectedParent)showChildren(selectedParent,false)}}
network.on("click",p=>{{if(p.nodes.length){{const n=nodes.get(p.nodes[0]);if(n&&["Router","Switch"].includes(n.deviceType))showChildren(n.id)}}else if(!p.edges.length)closePanel()}});
network.on("doubleClick",p=>{{if(!p.nodes.length)return;const n=nodes.get(p.nodes[0]);if(!n||n.id==="internet")return;if(["Router","Switch"].includes(n.deviceType))showChildren(n.id);else if(n.ip)location.href="/device/"+encodeURIComponent(n.ip)+"/"}});
async function updateDeviceStatus(){{try{{const r=await fetch("/api/topology/status/",{{cache:"no-store"}});if(!r.ok)return;const data=await r.json();data.forEach(d=>{{const n=allNodes.find(x=>String(x.ip)===String(d.ip_address));if(n)n.deviceStatus=String(d.status||"Offline").toLowerCase()}});applyFilter()}}catch(e){{console.error("Topology status update:",e)}}}}
updateDeviceStatus();setInterval(updateDeviceStatus,3000);setTimeout(fitNetwork,500);
</script></body></html>'''
    with open(OUTPUT_FILE,"w",encoding="utf-8") as f: f.write(html)
    print(f"Topology generated successfully: {OUTPUT_FILE}")

def main():
    generate_html(*build_topology())

if __name__=="__main__": main()

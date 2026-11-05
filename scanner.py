
import os,sys,re,json,ipaddress,subprocess
from concurrent.futures import ThreadPoolExecutor,as_completed
from django.db import transaction

BASE_DIR=os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path: sys.path.insert(0,BASE_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE","nms.settings")
import django
django.setup()
from django.utils import timezone
from dashboard.models import Device,DeviceLog,DeviceStats,DeviceStatsHistory

MAX_WORKERS=30
PING_TIMEOUT_MS=1000
POWERSHELL_TIMEOUT_SECONDS=60
HOTSPOT_SUBNET=ipaddress.ip_network("192.168.137.0/24")

def get_networks():
    print("\n[NETWORK] Detecting Windows Mobile Hotspot...")
    script=r"""
    $results=@()
    $adapters=Get-NetAdapter -ErrorAction Stop | Where-Object {
        $_.Status -eq 'Up' -and (
            $_.InterfaceDescription -match 'Wi-Fi Direct' -or
            $_.Name -like 'Local Area Connection*'
        )
    }
    foreach($adapter in $adapters){
        $addresses=Get-NetIPAddress -InterfaceIndex $adapter.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
        foreach($address in $addresses){
            if($address.IPAddress -like '169.254.*' -or $address.IPAddress -eq '127.0.0.1'){continue}
            $results+=@{
                InterfaceAlias=$adapter.Name
                InterfaceDescription=$adapter.InterfaceDescription
                InterfaceIndex=$adapter.ifIndex
                IPAddress=$address.IPAddress
                PrefixLength=$address.PrefixLength
            }
        }
    }
    ConvertTo-Json -InputObject $results -Compress
    """
    try:
        result=subprocess.run(["powershell.exe","-NoProfile","-NonInteractive","-Command",script],capture_output=True,text=True,timeout=POWERSHELL_TIMEOUT_SECONDS,creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode!=0: raise RuntimeError(result.stderr.strip())
        output=result.stdout.strip()
        if not output: raise RuntimeError("Windows Mobile Hotspot adapter not found.")
        data=json.loads(output)
        if isinstance(data,dict): data=[data]
        networks=[]
        for adapter in data or []:
            local_ip=adapter.get("IPAddress")
            if not local_ip: continue
            interface=ipaddress.ip_interface(f"{local_ip}/{int(adapter.get('PrefixLength',24))}")
            if interface.network!=HOTSPOT_SUBNET: continue
            networks.append({
                "interface":adapter.get("InterfaceAlias"),
                "description":adapter.get("InterfaceDescription"),
                "interface_index":adapter.get("InterfaceIndex"),
                "local_ip":local_ip,
                "network":interface.network
            })
        if not networks:
            raise RuntimeError(f"Hotspot subnet {HOTSPOT_SUBNET} was not found. Check that Windows Mobile Hotspot is enabled.")
        if len(networks)>1:
            networks.sort(key=lambda x:"Wi-Fi Direct" not in (x["description"] or ""),reverse=False)
            networks=networks[:1]
        return networks
    except subprocess.TimeoutExpired:
        raise RuntimeError("Windows adapter detection timed out.")
    except Exception as e:
        raise RuntimeError(f"Hotspot detection failed: {e}")

def ping_device(ip):
    try:
        result=subprocess.run(["ping","-n","1","-w",str(PING_TIMEOUT_MS),ip],capture_output=True,text=True,timeout=4,creationflags=subprocess.CREATE_NO_WINDOW)
        output=result.stdout.lower()
        if "reply from" not in output or "destination host unreachable" in output: return False,0
        match=re.search(r"time[=<]\s*(\d+)\s*ms",output)
        latency=float(match.group(1)) if match else (0.5 if "<1ms" in output else 0)
        return True,latency
    except subprocess.TimeoutExpired:
        return False,0
    except Exception as e:
        print(f"[PING ERROR] {ip}: {e}")
        return False,0

def get_arp_table():
    arp_table={}
    try:
        result=subprocess.run(["arp","-a"],capture_output=True,text=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
        for line in result.stdout.splitlines():
            match=re.search(r"(\d+\.\d+\.\d+\.\d+)\s+([0-9a-fA-F-]{17})",line)
            if match:
                ip=match.group(1)
                mac=match.group(2).replace("-",":").lower()
                if mac!="00:00:00:00:00:00": arp_table[ip]=mac
    except Exception as e:
        print(f"[ARP ERROR] {e}")
    return arp_table

def get_hostname(ip):
    try:
        result=subprocess.run(["nslookup",ip],capture_output=True,text=True,timeout=3,creationflags=subprocess.CREATE_NO_WINDOW)
        for line in result.stdout.splitlines():
            if "name =" in line.lower(): return line.split("=",1)[1].strip().rstrip(".")
    except Exception:
        pass
    return None

def update_device(ip,hostname,mac_address):
    now=timezone.now()
    with transaction.atomic():
        device,created=Device.objects.get_or_create(ip_address=ip,defaults={
            "hostname":hostname,
            "mac_address":mac_address,
            "status":"Online",
            "online_since":now,
            "last_seen":now,
            "last_uptime_seconds":0
        })
        if created:
            DeviceLog.objects.create(device=device,status="Online",message="New hotspot device detected")
            return device
        was_offline=device.status!="Online"
        if hostname: device.hostname=hostname
        if mac_address: device.mac_address=mac_address
        device.status="Online"
        device.last_seen=now
        if was_offline:
            device.online_since=now
            device.last_uptime_seconds=0
            DeviceLog.objects.create(device=device,status="Online",message="Hotspot device came back online")
        device.save()
        return device

def update_device_stats(device,latency_ms):
    now=timezone.now()
    stats,_=DeviceStats.objects.get_or_create(device=device)
    stats.packets_sent+=1
    stats.packets_received+=1
    stats.latency_ms=latency_ms
    stats.last_poll_time=now
    stats.save()
    DeviceStatsHistory.objects.create(device=device,timestamp=now,latency_ms=latency_ms,packets_sent=1,packets_received=1,packets_lost=0,packet_loss=0)

def generate_ips(network,local_ip):
    return [str(ip) for ip in network.hosts() if str(ip)!=local_ip]

def scan_single_network(network_info):
    interface=network_info["interface"]
    local_ip=network_info["local_ip"]
    network=network_info["network"]
    print(f"\n{'-'*40}")
    print(f"[SCANNING] Interface: {interface}")
    print(f"[SCANNING] Local IP : {local_ip}")
    print(f"[SCANNING] Network  : {network}")
    print(f"{'-'*40}")
    ips=generate_ips(network,local_ip)
    print(f"Scanning {len(ips)} hotspot client IP addresses...")
    online_devices=[]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures={executor.submit(ping_device,ip):ip for ip in ips}
        for future in as_completed(futures):
            ip=futures[future]
            try:
                is_online,latency=future.result()
                if is_online:
                    online_devices.append((ip,latency))
                    print(f"[ONLINE] {ip} ({latency} ms)")
            except Exception as e:
                print(f"[ERROR] {ip}: {e}")
    return {"interface":interface,"local_ip":local_ip,"network":network,"online_devices":online_devices}

def mark_offline_devices(online_ips,network,local_ip):
    for device in Device.objects.exclude(status="Offline"):
        ip=str(device.ip_address)
        try:
            if ipaddress.ip_address(ip) not in network or ip==local_ip: continue
        except ValueError:
            continue
        if ip not in online_ips:
            device.status="Offline"
            device.save(update_fields=["status"])
            DeviceLog.objects.create(device=device,status="Offline",message="Hotspot device did not respond to network scan")
            print(f"[OFFLINE] {ip}")

def scan_network():
    print("\n"+"="*45)
    print("       HOTSPOT DEVICE DISCOVERY")
    print("="*45)
    try:
        networks=get_networks()
    except Exception as e:
        print(f"\n[NETWORK ERROR] {e}")
        print("[DATABASE] Existing database NOT changed.")
        return
    network_info=networks[0]
    print("\n[HOTSPOT NETWORK]")
    print(f"Interface : {network_info['interface']}")
    print(f"Description: {network_info['description']}")
    print(f"Laptop IP : {network_info['local_ip']}")
    print(f"Subnet    : {network_info['network']}")
    result=scan_single_network(network_info)
    arp_table=get_arp_table()
    online_ips=set()
    total_online=0
    print(f"\n[DATABASE] Updating hotspot devices from {result['network']}")
    for ip,latency in result["online_devices"]:
        online_ips.add(ip)
        hostname=get_hostname(ip)
        mac_address=arp_table.get(ip)
        device=update_device(ip,hostname,mac_address)
        update_device_stats(device,latency)
        total_online+=1
    mark_offline_devices(online_ips,result["network"],result["local_ip"])
    hotspot_devices=Device.objects.filter(ip_address__startswith="192.168.137.")
    print("\n"+"="*45)
    print("       HOTSPOT SCAN COMPLETE")
    print("="*45)
    print(f"Hotspot subnet       : {result['network']}")
    print(f"Online clients found : {total_online}")
    print(f"Hotspot DB records   : {hotspot_devices.count()}")
    print(f"Total DB records     : {Device.objects.count()}")
    print("Other network records and historical data were not deleted.")
    print("Scanner stopped.")
    print("="*45)

if __name__=="__main__":
    scan_network()

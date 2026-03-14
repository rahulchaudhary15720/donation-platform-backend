"""
Database Connection Helper
Handles IPv6/IPv4 connectivity issues automatically
"""
import socket
import subprocess
import os

def check_ipv6_connectivity():
    """Check if system has IPv6 connectivity"""
    try:
        # Try to create an IPv6 socket and connect to Google DNS
        sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(("2001:4860:4860::8888", 80))
        sock.close()
        return True
    except:
        return False

def check_ipv4_connectivity():
    """Check if system has IPv4 connectivity"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect(("8.8.8.8", 80))
        sock.close()
        return True
    except:
        return False

def diagnose_connectivity():
    """Diagnose network connectivity"""
    print("\n" + "="*50)
    print("Network Connectivity Diagnostic")
    print("="*50)
    
    ipv4 = check_ipv4_connectivity()
    ipv6 = check_ipv6_connectivity()
    
    print(f"IPv4 Connectivity: {'✅ Available' if ipv4 else '❌ Not Available'}")
    print(f"IPv6 Connectivity: {'✅ Available' if ipv6 else '❌ Not Available'}")
    
    if not ipv6 and ipv4:
        print("\n⚠️  Your system has IPv4 but not IPv6 connectivity.")
        print("Supabase direct database connections require IPv6.")
        print("\nSolutions:")
        print("1. Use Supabase Connection Pooler (supports IPv4)")
        print("2. Enable IPv6 on your system/router")
        print("3. Use IPv6 tunnel service (like tunnelbroker.net)")
        print("4. Contact your ISP to enable IPv6")
    
    return ipv4, ipv6

def get_connection_instructions():
    """Provide instructions for fixing connection issues"""
    return """
╔══════════════════════════════════════════════════════════════╗
║         SUPABASE CONNECTION FIX - IPv6 ISSUE                 ║
╚══════════════════════════════════════════════════════════════╝

Your system doesn't have IPv6 connectivity, but Supabase requires it.

SOLUTION 1: Use Connection Pooler (Recommended)
------------------------------------------------
Update your .env DATABASE_URL to use the pooler:

Old format:
  postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres

New format (use port 6543 and add your project ref):
  postgresql://postgres.[REF]:[PASSWORD]@aws-0-ap-south-1.pooler.supabase.com:6543/postgres

SOLUTION 2: Enable IPv6 on Linux
---------------------------------
1. Check if IPv6 is disabled:
   cat /proc/sys/net/ipv6/conf/all/disable_ipv6

2. If it shows '1', enable IPv6 temporarily:
   sudo sysctl -w net.ipv6.conf.all.disable_ipv6=0
   sudo sysctl -w net.ipv6.conf.default.disable_ipv6=0

3. Test connection again

SOLUTION 3: Use Supabase Dashboard
-----------------------------------
1. Go to Settings > Database in your Supabase dashboard
2. Look for "Connection Pooler" section
3. Copy the "Connection string" (it should use the pooler)

Need help finding your connection string?
Visit: https://supabase.com/dashboard/project/[your-project]/settings/database
"""


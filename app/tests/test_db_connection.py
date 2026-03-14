#!/usr/bin/env python3
"""
Database Connection Diagnostic Tool
Tests various connection methods to help diagnose issues
"""

import sys
import psycopg2
from sqlalchemy import create_engine, text
from app.core.config import settings

def test_direct_psycopg2():
    """Test direct psycopg2 connection"""
    print("\n" + "="*50)
    print("Test 1: Direct psycopg2 connection")
    print("="*50)
    
    try:
        # Parse the connection string
        db_url = settings.DATABASE_URL
        print(f"Database URL: {db_url.split('@')[1] if '@' in db_url else 'hidden'}")
        
        # Try to connect
        conn = psycopg2.connect(settings.DATABASE_URL, connect_timeout=10)
        print("✅ Connection successful!")
        
        # Test a simple query
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"✅ PostgreSQL version: {version[0][:50]}...")
        
        cursor.close()
        conn.close()
        return True
        
    except psycopg2.OperationalError as e:
        print(f"❌ Connection failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def test_sqlalchemy():
    """Test SQLAlchemy connection"""
    print("\n" + "="*50)
    print("Test 2: SQLAlchemy connection")
    print("="*50)
    
    try:
        engine = create_engine(
            settings.DATABASE_URL,
            connect_args={"connect_timeout": 10},
            pool_pre_ping=True
        )
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✅ SQLAlchemy connection successful!")
            return True
            
    except Exception as e:
        print(f"❌ SQLAlchemy connection failed: {e}")
        return False

def test_dns_resolution():
    """Test DNS resolution of the database host"""
    print("\n" + "="*50)
    print("Test 3: DNS Resolution")
    print("="*50)
    
    import socket
    
    try:
        # Extract hostname from DATABASE_URL
        db_url = settings.DATABASE_URL
        hostname = db_url.split('@')[1].split(':')[0] if '@' in db_url else None
        
        if not hostname:
            print("❌ Could not extract hostname from DATABASE_URL")
            return False
        
        print(f"Resolving: {hostname}")
        
        # Get all IP addresses
        addr_info = socket.getaddrinfo(hostname, 5432, socket.AF_UNSPEC, socket.SOCK_STREAM)
        
        print(f"✅ DNS resolution successful! Found {len(addr_info)} address(es):")
        for info in addr_info:
            family = "IPv6" if info[0] == socket.AF_INET6 else "IPv4"
            print(f"  - {family}: {info[4][0]}")
        
        return True
        
    except socket.gaierror as e:
        print(f"❌ DNS resolution failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

def suggest_solutions():
    """Provide troubleshooting suggestions"""
    print("\n" + "="*50)
    print("Troubleshooting Suggestions")
    print("="*50)
    print("""
    If IPv6 is failing but IPv4 works:
    1. Your system might not have IPv6 connectivity
    2. Try adding '?host=db.ovheeibiatuhybezykzx.supabase.co' with explicit IPv4
    
    If all connections fail:
    1. Check Supabase dashboard - database might be paused
    2. Verify database credentials in .env file
    3. Check firewall/network settings
    4. Ensure port 5432 is not blocked
    
    If DNS resolution fails:
    1. Check internet connectivity
    2. Try accessing Supabase dashboard in browser
    3. Check DNS settings
    """)

def main():
    print("="*50)
    print("Database Connection Diagnostic Tool")
    print("="*50)
    
    results = []
    
    # Run tests
    results.append(("DNS Resolution", test_dns_resolution()))
    results.append(("Direct psycopg2", test_direct_psycopg2()))
    results.append(("SQLAlchemy", test_sqlalchemy()))
    
    # Summary
    print("\n" + "="*50)
    print("Summary")
    print("="*50)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name}: {status}")
    
    if not any(result for _, result in results):
        suggest_solutions()
        sys.exit(1)
    else:
        print("\n✅ At least one connection method worked!")
        sys.exit(0)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Script to check referral system status."""

import asyncio
import httpx
from app.config import get_settings

settings = get_settings()

def get_api_url(path: str) -> str:
    base = settings.api_base_url.rstrip("/")
    return f"{base}/api/v1{path}"

async def check_referrals():
    """Check referral system."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Check a specific user's referral stats
        print("=== Referral System Check ===\n")
        
        # You can change this user_id to check a specific user
        test_user_id = input("Enter user_id to check (or press Enter for example): ").strip()
        if not test_user_id:
            print("No user_id provided. Usage:")
            print("  python check_referrals.py")
            print("  Then enter a user_id when prompted")
            return
        
        try:
            user_id = int(test_user_id)
        except ValueError:
            print(f"Invalid user_id: {test_user_id}")
            return
        
        # 1. Check user exists and has referral_code
        print(f"\n1. Checking user {user_id}...")
        try:
            response = await client.get(get_api_url(f"/users/{user_id}/balance"))
            if response.status_code == 200:
                user_data = response.json()
                print(f"   ✓ User exists")
                print(f"   - Balance: {user_data.get('checks_balance', 0)}")
                print(f"   - Referral code: {user_data.get('referral_code', 'N/A')}")
            else:
                print(f"   ✗ User not found: {response.status_code}")
                return
        except Exception as e:
            print(f"   ✗ Error: {e}")
            return
        
        # 2. Check referral stats
        print(f"\n2. Checking referral stats...")
        try:
            response = await client.get(
                get_api_url("/referrals/stats"),
                params={"user_id": user_id}
            )
            if response.status_code == 200:
                stats = response.json()
                print(f"   ✓ Stats retrieved")
                print(f"   - Total referrals: {stats.get('total_referrals', 0)}")
                print(f"   - Referrals for bonus: {stats.get('referrals_for_bonus', 0)}")
                print(f"   - Bonus progress: {stats.get('bonus_progress', 0)}")
                print(f"   - Total bonuses earned: {stats.get('total_bonuses_earned', 0)}")
                print(f"   - Referral link: {stats.get('referral_link', 'N/A')}")
            else:
                print(f"   ✗ Error getting stats: {response.status_code}")
                print(f"   Response: {response.text}")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        # 3. Check referral list
        print(f"\n3. Checking referral list...")
        try:
            response = await client.get(
                get_api_url("/referrals/list"),
                params={"user_id": user_id, "limit": 10}
            )
            if response.status_code == 200:
                result = response.json()
                referrals = result.get('referrals', [])
                print(f"   ✓ List retrieved")
                print(f"   - Total referrals: {result.get('total', 0)}")
                if referrals:
                    print(f"   - Recent referrals:")
                    for ref in referrals[:5]:
                        print(f"     • @{ref.get('referred_username', 'N/A')} "
                              f"(ID: {ref.get('referred_user_id')}, "
                              f"bonus: {ref.get('bonus_granted', False)})")
                else:
                    print(f"   - No referrals found")
            else:
                print(f"   ✗ Error getting list: {response.status_code}")
                print(f"   Response: {response.text}")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        print("\n=== Check complete ===")

if __name__ == "__main__":
    asyncio.run(check_referrals())


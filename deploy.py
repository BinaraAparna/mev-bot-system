"""
Contract Deployment Wrapper
Runs scripts/deploy_contract.py
"""

import subprocess
import sys

if __name__ == "__main__":
    print("=" * 70)
    print("MEV Bot Contract Deployment")
    print("=" * 70)
    print()
    
    # Run deployment script
    result = subprocess.run(
        [sys.executable, "scripts/deploy_contract.py"],
        cwd="."
    )
    
    sys.exit(result.returncode)
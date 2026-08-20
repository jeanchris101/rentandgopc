#!/bin/bash
# Deploy FB scraper to DigitalOcean VPS (144.172.100.16)
# Run this FROM the VPS after cloning/copying the files

set -e

echo "=== FB Scraper VPS Setup ==="

# Install dependencies
apt-get update -qq
apt-get install -y -qq python3-pip xvfb > /dev/null 2>&1

# Create project directory
mkdir -p /opt/fb_scraper/sessions
mkdir -p /opt/fb_scraper/data

# Install Python packages
pip3 install patchright --break-system-packages 2>/dev/null || pip3 install patchright

# Install Chromium for Patchright
python3 -m patchright install chromium
python3 -m patchright install-deps chromium 2>/dev/null || true

echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. Copy scraper files to /opt/fb_scraper/"
echo "  2. Run: cd /opt/fb_scraper && python3 scraper.py setup burner1"
echo "     (This will auto-login and save the session)"
echo "  3. Run: python3 scraper.py join"
echo "     (Auto-join the 4 target groups)"
echo "  4. Test: python3 scraper.py scrape --visible"
echo "  5. Set up cron: crontab -e"
echo '     0 10 * * * cd /opt/fb_scraper && xvfb-run python3 scraper.py scrape >> /var/log/fb_scraper.log 2>&1'
